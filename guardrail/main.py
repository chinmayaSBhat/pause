# Pause - Financial Discipline App
from fastapi import FastAPI, Request, Form, Depends, Cookie, HTTPException, status, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from passlib.context import CryptContext

from starlette.middleware.sessions import SessionMiddleware
from authlib.integrations.starlette_client import OAuth
from starlette.config import Config
from dotenv import load_dotenv
import os

load_dotenv()

from database import engine, Base, get_db, User, WishlistItem, DailyLog, SavingGoal, BehavioralAllocation

# Create the database tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Pause")
app.add_middleware(SessionMiddleware, secret_key="super-secret-key-for-oauth")

templates = Jinja2Templates(directory="templates")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Setup Authlib OAuth
config = Config('.env')
oauth = OAuth(config)
oauth.register(
    name='google',
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={
        'scope': 'openid email profile'
    }
)

# Custom exception handler for redirects
@app.exception_handler(status.HTTP_307_TEMPORARY_REDIRECT)
async def redirect_exception_handler(request: Request, exc: HTTPException):
    return RedirectResponse(url=exc.headers.get("Location"), status_code=303)

def get_current_user(request: Request, db: Session = Depends(get_db)):
    session_id = request.cookies.get("session_id")
    if session_id:
        user = db.query(User).filter(User.user_id == session_id).first()
        if user:
            return user
    raise HTTPException(status_code=status.HTTP_307_TEMPORARY_REDIRECT, headers={"Location": "/login"})

@app.get("/", response_class=HTMLResponse)
async def read_dashboard(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    
    # Simplified streak calculation
    logs = db.query(DailyLog).filter(DailyLog.user_id == user.user_id, DailyLog.is_no_spend_day == 1).order_by(DailyLog.log_date.desc()).all()
    streak = len(logs)

    cooling_items = db.query(WishlistItem).filter(
        WishlistItem.user_id == user.user_id,
        WishlistItem.status == "COOLING"
    ).order_by(WishlistItem.timer_expires_at.asc()).all()

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html", 
        context={"user": user, "streak": streak, "items": cooling_items}
    )

@app.post("/intercept")
async def intercept_purchase(
    item_name: str = Form(...),
    price: float = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    income = user.monthly_income if user.monthly_income and user.monthly_income > 0 else 4800.0
    hours = user.work_hours_per_week if user.work_hours_per_week and user.work_hours_per_week > 0 else 40.0
    wage = income / (hours * 4)
    hours_to_earn = round(price / wage, 2)
    
    timer_expires_at = datetime.utcnow() + timedelta(hours=48)
    
    new_item = WishlistItem(
        user_id=user.user_id,
        item_name=item_name,
        price=price,
        hours_to_earn=hours_to_earn,
        status="COOLING",
        timer_expires_at=timer_expires_at
    )
    db.add(new_item)
    db.commit()
    
    return RedirectResponse(url="/", status_code=303)

@app.post("/update-item/{item_id}")
async def update_item(
    item_id: str,
    action: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    item = db.query(WishlistItem).filter(WishlistItem.item_id == item_id).first()
    if item:
        if action == 'SAVED':
            item.status = 'SAVED'
        elif action == 'BOUGHT':
            item.status = 'BOUGHT'
        db.commit()
    
    return RedirectResponse(url="/", status_code=303)

@app.get("/profile", response_class=HTMLResponse)
async def read_profile(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    allocations = db.query(BehavioralAllocation).filter(BehavioralAllocation.user_id == user.user_id).all()
    alloc_dict = {a.category: a.percentage for a in allocations}
    return templates.TemplateResponse(request=request, name="profile.html", context={"user": user, "alloc_dict": alloc_dict})

@app.post("/profile")
async def update_profile(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    form_data = await request.form()
    
    user.monthly_income = float(form_data.get("monthly_income", 0.0) or 0.0)
    user.work_hours_per_week = float(form_data.get("work_hours_per_week", 40.0) or 40.0)
    user.expense_rent = float(form_data.get("expense_rent", 0.0) or 0.0)
    user.expense_emi = float(form_data.get("expense_emi", 0.0) or 0.0)
    user.expense_subscriptions = float(form_data.get("expense_subscriptions", 0.0) or 0.0)
    user.expense_savings_sip = float(form_data.get("expense_savings_sip", 0.0) or 0.0)
    user.expense_other = float(form_data.get("expense_other", 0.0) or 0.0)
    
    db.query(BehavioralAllocation).filter(BehavioralAllocation.user_id == user.user_id).delete()
    
    categories = ["Online Shopping", "Daily Food & Coffee", "Subscribed Leakage", "Impulse Buying", "Entertainment"]
    for cat in categories:
        val = form_data.get(f"alloc_{cat}")
        if val:
            try:
                pct = float(val)
                if pct > 0:
                    alloc = BehavioralAllocation(user_id=user.user_id, category=cat, percentage=pct)
                    db.add(alloc)
            except ValueError:
                pass
                
    db.commit()
    return RedirectResponse(url="/profile", status_code=303)

@app.get("/goals", response_class=HTMLResponse)
async def read_goals(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    goals = db.query(SavingGoal).filter(SavingGoal.user_id == user.user_id).order_by(SavingGoal.end_date.desc()).all()
    
    from datetime import date, timedelta
    today = date.today()
    start_of_week = today - timedelta(days=today.weekday())
    
    saved_items = db.query(WishlistItem).filter(
        WishlistItem.user_id == user.user_id,
        WishlistItem.status == 'SAVED',
        WishlistItem.created_at >= datetime.combine(start_of_week, datetime.min.time())
    ).all()
    
    saved_this_week = sum(item.price for item in saved_items)
    
    return templates.TemplateResponse(request=request, name="goals.html", context={"user": user, "goals": goals, "saved_this_week": saved_this_week})

@app.post("/goals")
async def create_goal(
    goal_amount: float = Form(...),
    days: int = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    from datetime import date, timedelta
    end_date = date.today() + timedelta(days=days)
    new_goal = SavingGoal(user_id=user.user_id, goal_amount=goal_amount, end_date=end_date)
    db.add(new_goal)
    db.commit()
    return RedirectResponse(url="/goals", status_code=303)

@app.get("/achievements", response_class=HTMLResponse)
async def read_achievements(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    
    saved_items = db.query(WishlistItem).filter(
        WishlistItem.user_id == user.user_id,
        WishlistItem.status == 'SAVED'
    ).all()
    
    total_rupees_saved = sum(item.price for item in saved_items)
    total_hours_saved = sum(item.hours_to_earn for item in saved_items)
    
    logs = db.query(DailyLog).filter(DailyLog.user_id == user.user_id, DailyLog.is_no_spend_day == 1).order_by(DailyLog.log_date.desc()).all()
    streak = len(logs)
    
    badges = []
    upcoming = []
    
    if streak >= 3:
        badges.append({"name": "Weekend Warrior", "desc": "3 Day No-Spend Streak", "icon": "🛡️"})
    else:
        upcoming.append({"name": "Weekend Warrior", "desc": f"{3 - streak} more days for a 3-Day Streak", "icon": "🛡️"})
        
    if streak >= 7:
        badges.append({"name": "Iron Will", "desc": "7 Day No-Spend Streak", "icon": "⚔️"})
    elif streak >= 3:
        upcoming.append({"name": "Iron Will", "desc": f"{7 - streak} more days for a 7-Day Streak", "icon": "⚔️"})
        
    if total_rupees_saved >= 1000:
        badges.append({"name": "First K", "desc": "Saved ₹1,000", "icon": "💰"})
    else:
        upcoming.append({"name": "First K", "desc": f"Save ₹{1000 - total_rupees_saved:,.0f} more", "icon": "💰"})
        
    if total_rupees_saved >= 5000:
        badges.append({"name": "5K Club", "desc": "Saved ₹5,000", "icon": "💎"})
    elif total_rupees_saved >= 1000:
        upcoming.append({"name": "5K Club", "desc": f"Save ₹{5000 - total_rupees_saved:,.0f} more", "icon": "💎"})
        
    if total_hours_saved >= 24:
        badges.append({"name": "Day Reclaimed", "desc": "Saved 24 hours of labor", "icon": "⏳"})
    else:
        upcoming.append({"name": "Day Reclaimed", "desc": f"Save {24 - total_hours_saved:,.1f} more hours", "icon": "⏳"})
        
    return templates.TemplateResponse(
        request=request, 
        name="achievements.html", 
        context={
            "user": user, 
            "total_rupees": total_rupees_saved, 
            "total_hours": total_hours_saved,
            "badges": badges,
            "upcoming": upcoming,
            "streak": streak
        }
    )

@app.get('/login/google')
async def login_google(request: Request):
    # Ensure redirect_uri uses https if coming from ngrok, otherwise use request.base_url
    base_url = str(request.base_url).rstrip("/")
    if "ngrok" in base_url and base_url.startswith("http://"):
        base_url = base_url.replace("http://", "https://")
    redirect_uri = base_url + "/auth/google"
    return await oauth.google.authorize_redirect(request, redirect_uri)

@app.get('/auth/google')
async def auth_google(request: Request, db: Session = Depends(get_db)):
    try:
        token = await oauth.google.authorize_access_token(request)
    except Exception:
        return RedirectResponse(url='/login', status_code=303)
        
    userinfo = token.get('userinfo')
    if not userinfo:
        return RedirectResponse(url='/login', status_code=303)
        
    email = userinfo.get('email')
    name = userinfo.get('name')
    
    if not email:
        return RedirectResponse(url='/login', status_code=303)
        
    user = db.query(User).filter(User.username == email).first()
    if not user:
        user = User(username=email, first_name=name, monthly_income=0.0)
        db.add(user)
        db.commit()
        db.refresh(user)
        
    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(key="session_id", value=user.user_id, httponly=True)
    return response

@app.get("/login", response_class=HTMLResponse)
async def read_login(request: Request):
    return templates.TemplateResponse(request=request, name="login.html", context={})

@app.post("/login")
async def process_login(
    request: Request,
    response: Response,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    password = password[:72]
    user = db.query(User).filter(User.username == username).first()
    if not user or not pwd_context.verify(password, user.password_hash):
        return templates.TemplateResponse(request=request, name="login.html", context={"error": "Invalid username or password"})
    
    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(key="session_id", value=user.user_id, httponly=True)
    return response

@app.post("/signup")
async def process_signup(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    full_name: str = Form(...),
    db: Session = Depends(get_db)
):
    if password != confirm_password:
        return templates.TemplateResponse(request=request, name="login.html", context={"error": "Passwords do not match"})
        
    existing = db.query(User).filter(User.username == username).first()
    if existing:
        return templates.TemplateResponse(request=request, name="login.html", context={"error": "Username already taken"})
        
    password = password[:72]
    hashed = pwd_context.hash(password)
    new_user = User(username=username, password_hash=hashed, first_name=full_name, monthly_income=0.0)
    db.add(new_user)
    db.commit()
    
    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(key="session_id", value=new_user.user_id, httponly=True)
    return response

@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("session_id")
    return response
