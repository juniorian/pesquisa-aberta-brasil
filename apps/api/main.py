from fastapi import FastAPI, Depends, Query, Header, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from sqlalchemy.orm import Session

from database import engine, Base, get_db
import models

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Pesquisa Aberta Brasil API")

# ---------- AUTH DEPENDENCY ----------
def get_current_user(authorization: str = Header(None), db: Session = Depends(get_db)):
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing token")

    token = authorization.replace("Bearer ", "")
    user = db.query(models.User).filter(models.User.id == token).first()

    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")

    return user

# ---------- Schemas ----------
class UserCreate(BaseModel):
    username: str
    password: str

class UserOut(BaseModel):
    id: str
    username: str

class ArticleCreate(BaseModel):
    title: str
    content: str
    author: Optional[str] = None
    tags: List[str] = []

class ArticleOut(ArticleCreate):
    id: str

class WikiCreate(BaseModel):
    slug: str
    title: str
    content: str

class WikiOut(WikiCreate):
    pass

# ---------- AUTH ----------
@app.post("/auth/register", response_model=UserOut)
def register(user: UserCreate, db: Session = Depends(get_db)):
    existing = db.query(models.User).filter(models.User.username == user.username).first()
    if existing:
        return {"error": "user exists"}

    db_user = models.User(username=user.username, password=user.password)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return {"id": db_user.id, "username": db_user.username}

@app.post("/auth/login")
def login(user: UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.username == user.username).first()

    if not db_user or db_user.password != user.password:
        return {"error": "invalid credentials"}

    return {"message": "login successful", "token": db_user.id}

# ---------- ARTICLES (PROTECTED) ----------
@app.post("/articles", response_model=ArticleOut)
def create_article(
    article: ArticleCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user)
):
    db_article = models.Article(
        title=article.title,
        content=article.content,
        author=user.username,
        user_id=user.id,
        tags=",".join(article.tags) if article.tags else None
    )
    db.add(db_article)
    db.commit()
    db.refresh(db_article)
    return ArticleOut(
        id=db_article.id,
        title=db_article.title,
        content=db_article.content,
        author=db_article.author,
        tags=db_article.tags.split(",") if db_article.tags else []
    )

@app.get("/articles", response_model=List[ArticleOut])
def list_articles(db: Session = Depends(get_db)):
    articles = db.query(models.Article).all()
    return [
        ArticleOut(
            id=a.id,
            title=a.title,
            content=a.content,
            author=a.author,
            tags=a.tags.split(",") if a.tags else []
        )
        for a in articles
    ]

@app.get("/articles/{article_id}")
def get_article(article_id: str, db: Session = Depends(get_db)):
    a = db.query(models.Article).filter(models.Article.id == article_id).first()
    if not a:
        return {"error": "not found"}

    return ArticleOut(
        id=a.id,
        title=a.title,
        content=a.content,
        author=a.author,
        tags=a.tags.split(",") if a.tags else []
    )

# ---------- WIKI ----------
@app.post("/wiki", response_model=WikiOut)
def create_wiki(page: WikiCreate, db: Session = Depends(get_db)):
    db_page = models.WikiPage(
        slug=page.slug,
        title=page.title,
        content=page.content
    )
    db.add(db_page)
    db.commit()
    db.refresh(db_page)
    return page

@app.get("/wiki")
def list_wiki(db: Session = Depends(get_db)):
    return db.query(models.WikiPage).all()

@app.get("/wiki/{slug}")
def get_wiki(slug: str, db: Session = Depends(get_db)):
    page = db.query(models.WikiPage).filter(models.WikiPage.slug == slug).first()
    if not page:
        return {"error": "not found"}
    return page

@app.put("/wiki/{slug}")
def update_wiki(slug: str, page: WikiCreate, db: Session = Depends(get_db)):
    db_page = db.query(models.WikiPage).filter(models.WikiPage.slug == slug).first()
    if not db_page:
        return {"error": "not found"}

    db_page.title = page.title
    db_page.content = page.content
    db.commit()
    db.refresh(db_page)
    return db_page

# ---------- SEARCH ----------
@app.get("/search")
def search(q: str, db: Session = Depends(get_db)):
    query = f"%{q}%"

    articles = db.query(models.Article).filter(
        models.Article.title.ilike(query) |
        models.Article.content.ilike(query)
    ).all()

    wiki_pages = db.query(models.WikiPage).filter(
        models.WikiPage.title.ilike(query) |
        models.WikiPage.content.ilike(query)
    ).all()

    return {
        "articles": [
            {"id": a.id, "title": a.title, "type": "article"}
            for a in articles
        ],
        "wiki": [
            {"slug": w.slug, "title": w.title, "type": "wiki"}
            for w in wiki_pages
        ]
    }