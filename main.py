from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, HTMLResponse
from sqlalchemy.orm import Session
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from typing import Dict, List
from datetime import datetime
import uuid
import logging
import os

os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'

from config import get_settings
from database import get_db, engine
from models import Base, User, Job, Category, JobStatus, ModelMode, EmailScope
from auth import (
    get_oauth_flow,
    create_access_token,
    encrypt_token,
    get_current_user,
    get_google_credentials,
)
from workers import classify_emails_task
from classifier import EmailClassifier

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

settings = get_settings()

# Create tables
Base.metadata.create_all(bind=engine)

# Initialize app
app = FastAPI(title=settings.APP_NAME, version=settings.APP_VERSION)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Initialize categories
@app.on_event("startup")
async def startup_event():
    with next(get_db()) as db:
        for cat_name, cat_data in EmailClassifier.CATEGORIES.items():
            existing = db.query(Category).filter(Category.name == cat_name).first()
            if not existing:
                category = Category(
                    name=cat_name,
                    color=cat_data["color"],
                    description=f"{cat_name.capitalize()} emails",
                    gmail_label=f"Cloudidian/{cat_name.capitalize()}",
                )
                db.add(category)
        db.commit()
    logger.info("Application started")


# Health check
@app.get("/health")
async def health_check():
    return {"status": "online", "version": settings.APP_VERSION}


# OAuth routes
@app.get("/auth/google/start")
async def start_oauth():
    flow = get_oauth_flow()
    authorization_url, state = flow.authorization_url(
        access_type="offline", prompt="consent", include_granted_scopes="true"
    )
    return {"authorization_url": authorization_url, "state": state}


@app.get("/auth/google/callback")
async def oauth_callback(code: str = None, state: str = None, error: str = None, db: Session = Depends(get_db)):
    if error:
        logger.error(f"OAuth error: {error}")
        return HTMLResponse(content=f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Authentication Failed</title>
            <style>
                body {{
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    min-height: 100vh;
                    margin: 0;
                }}
                .container {{
                    background: white;
                    padding: 40px;
                    border-radius: 16px;
                    box-shadow: 0 10px 40px rgba(0,0,0,0.2);
                    text-align: center;
                    max-width: 500px;
                }}
                .error-icon {{
                    font-size: 64px;
                    color: #f56565;
                    margin-bottom: 20px;
                }}
                h1 {{
                    color: #2d3748;
                    margin-bottom: 20px;
                }}
                .error-message {{
                    color: #718096;
                    margin-bottom: 30px;
                    line-height: 1.6;
                }}
                .close-btn {{
                    background: linear-gradient(135deg, #4361ee, #3a0ca3);
                    color: white;
                    border: none;
                    padding: 12px 32px;
                    border-radius: 8px;
                    font-size: 16px;
                    cursor: pointer;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="error-icon">✗</div>
                <h1>Authentication Failed</h1>
                <div class="error-message">
                    Error: {error}
                </div>
                <button class="close-btn" onclick="window.close()">Close</button>
            </div>
        </body>
        </html>
        """, status_code=400)
    
    if not code:
        logger.error("No authorization code received")
        return HTMLResponse(content="No authorization code received", status_code=400)
    
    try:
        logger.info(f"OAuth callback received with code: {code[:20]}...")
        
        flow = get_oauth_flow()
        flow.fetch_token(code=code)
        credentials = flow.credentials
        
        logger.info("Token received successfully")

        user_info_service = build("oauth2", "v2", credentials=credentials, cache_discovery=False)
        user_info = user_info_service.userinfo().get().execute()

        user_id = user_info["id"]
        email = user_info["email"]
        name = user_info.get("name", "")
        picture = user_info.get("picture", "")
        
        logger.info(f"User info received: {email}")

        user = db.query(User).filter(User.id == user_id).first()
        if user:
            user.encrypted_access_token = encrypt_token(credentials.token)
            user.encrypted_refresh_token = (
                encrypt_token(credentials.refresh_token) if credentials.refresh_token else None
            )
            user.token_expiry = credentials.expiry
            user.last_login = datetime.utcnow()
            user.name = name
            user.picture = picture
            logger.info(f"Updated existing user: {email}")
        else:
            user = User(
                id=user_id,
                email=email,
                name=name,
                picture=picture,
                encrypted_access_token=encrypt_token(credentials.token),
                encrypted_refresh_token=(
                    encrypt_token(credentials.refresh_token) if credentials.refresh_token else None
                ),
                token_expiry=credentials.expiry,
                last_login=datetime.utcnow(),
            )
            db.add(user)
            logger.info(f"Created new user: {email}")

        db.commit()
        logger.info("Database commit successful")

        access_token = create_access_token(data={"sub": user_id, "email": email})
        logger.info("JWT token created")

        # FIXED: Return HTML that properly communicates with Chrome extension
        return HTMLResponse(content=f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Authentication Successful</title>
            <meta charset="UTF-8">
            <style>
                body {{
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    min-height: 100vh;
                    margin: 0;
                }}
                .container {{
                    background: white;
                    padding: 40px;
                    border-radius: 16px;
                    box-shadow: 0 10px 40px rgba(0,0,0,0.2);
                    text-align: center;
                    max-width: 500px;
                }}
                .success-icon {{
                    font-size: 64px;
                    color: #4361ee;
                    margin-bottom: 20px;
                }}
                h1 {{
                    color: #2d3748;
                    margin-bottom: 10px;
                }}
                .email {{
                    color: #4361ee;
                    font-weight: 600;
                    margin-bottom: 20px;
                }}
                .instructions {{
                    color: #718096;
                    margin-bottom: 30px;
                    line-height: 1.6;
                }}
                .close-btn {{
                    background: linear-gradient(135deg, #4361ee, #3a0ca3);
                    color: white;
                    border: none;
                    padding: 12px 32px;
                    border-radius: 8px;
                    font-size: 16px;
                    cursor: pointer;
                    transition: transform 0.2s;
                }}
                .close-btn:hover {{
                    transform: translateY(-2px);
                }}
                .token-saved {{
                    background: #f0fdf4;
                    border: 1px solid #86efac;
                    color: #166534;
                    padding: 12px;
                    border-radius: 8px;
                    margin-top: 20px;
                    font-size: 14px;
                }}
                .status {{
                    margin-top: 10px;
                    font-size: 14px;
                    color: #666;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="success-icon">✓</div>
                <h1>Authentication Successful!</h1>
                <div class="email">Logged in as: {email}</div>
                <div class="instructions">
                    Your Gmail account has been connected successfully.<br>
                    This window will close automatically.
                </div>
                <div class="token-saved">
                    ✓ Authentication token saved securely
                </div>
                <div class="status" id="status">Saving authentication...</div>
                <button class="close-btn" onclick="window.close()" style="margin-top: 20px;">Close This Tab</button>
            </div>
            <script>
                (function() {{
                    const authData = {{
                        token: '{access_token}',
                        user: {{
                            id: '{user_id}',
                            email: '{email}',
                            name: '{name}',
                            picture: '{picture}'
                        }}
                    }};
                    
                    const statusEl = document.getElementById('status');
                    
                    // Method 1: Use localStorage as a bridge (most reliable)
                    try {{
                        localStorage.setItem('cloudidian_auth_pending', JSON.stringify(authData));
                        localStorage.setItem('cloudidian_auth_timestamp', Date.now().toString());
                        statusEl.textContent = '✓ Auth data saved to localStorage';
                        console.log('✓ Saved to localStorage');
                    }} catch (e) {{
                        console.error('localStorage failed:', e);
                        statusEl.textContent = '⚠ localStorage not available';
                    }}
                    
                    // Method 2: Try to communicate with extension via window.postMessage
                    try {{
                        window.postMessage({{
                            type: 'CLOUDIDIAN_AUTH_SUCCESS',
                            source: 'cloudidian-oauth-callback',
                            data: authData
                        }}, '*');
                        console.log('✓ Posted message to window');
                    }} catch (e) {{
                        console.error('postMessage failed:', e);
                    }}
                    
                    // Method 3: If opened by the extension, message back to opener
                    if (window.opener) {{
                        try {{
                            window.opener.postMessage({{
                                type: 'CLOUDIDIAN_AUTH_SUCCESS',
                                source: 'cloudidian-oauth-callback',
                                data: authData
                            }}, '*');
                            console.log('✓ Sent message to opener window');
                        }} catch (e) {{
                            console.error('opener.postMessage failed:', e);
                        }}
                    }}
                    
                    // Log the auth data for debugging
                    console.log('Authentication successful:', {{
                        email: authData.user.email,
                        userId: authData.user.id,
                        tokenLength: authData.token.length
                    }});
                    
                    // Auto-close after 3 seconds
                    setTimeout(() => {{
                        statusEl.textContent = 'Closing window...';
                        window.close();
                    }}, 3000);
                }})();
            </script>
        </body>
        </html>
        """)

    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        logger.error(f"OAuth callback error: {e}")
        logger.error(f"Full traceback:\n{error_trace}")
        
        error_message = str(e).replace("'", "\\'").replace('"', '\\"').replace('\n', ' ')[:200]
        
        return HTMLResponse(content=f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Authentication Failed</title>
            <style>
                body {{
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    min-height: 100vh;
                    margin: 0;
                }}
                .container {{
                    background: white;
                    padding: 40px;
                    border-radius: 16px;
                    box-shadow: 0 10px 40px rgba(0,0,0,0.2);
                    text-align: center;
                    max-width: 500px;
                }}
                .error-icon {{
                    font-size: 64px;
                    color: #f56565;
                    margin-bottom: 20px;
                }}
                h1 {{
                    color: #2d3748;
                    margin-bottom: 20px;
                }}
                .error-message {{
                    color: #718096;
                    margin-bottom: 30px;
                    line-height: 1.6;
                }}
                .close-btn {{
                    background: linear-gradient(135deg, #4361ee, #3a0ca3);
                    color: white;
                    border: none;
                    padding: 12px 32px;
                    border-radius: 8px;
                    font-size: 16px;
                    cursor: pointer;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="error-icon">✗</div>
                <h1>Authentication Failed</h1>
                <div class="error-message">
                    {error_message}
                    <br><br>
                    Please try again or check the backend logs for details.
                </div>
                <button class="close-btn" onclick="window.close()">Close</button>
            </div>
        </body>
        </html>
        """, status_code=500)


# User routes
@app.get("/api/user/me")
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "email": current_user.email,
        "name": current_user.name,
        "picture": current_user.picture,
    }


# Job routes
@app.post("/api/jobs/start")
async def start_classification_job(
    request: Dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    mode = request.get("mode", "fast")
    scope = request.get("scope", "unread")

    if mode not in [m.value for m in ModelMode]:
        raise HTTPException(status_code=400, detail="Invalid mode")
    if scope not in [s.value for s in EmailScope]:
        raise HTTPException(status_code=400, detail="Invalid scope")

    job_id = str(uuid.uuid4())
    job = Job(
        id=job_id,
        user_id=current_user.id,
        mode=mode,
        scope=scope,
        status=JobStatus.PENDING,
    )
    db.add(job)
    db.commit()

    # Start Celery task
    task = classify_emails_task.delay(job_id, current_user.id, mode, scope)

    job.celery_task_id = task.id
    db.commit()

    logger.info(f"Started job {job_id} for user {current_user.email}")

    return {
        "job_id": job_id,
        "status": job.status,
        "task_id": task.id,
    }


@app.get("/api/jobs/{job_id}")
async def get_job_status(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    job = db.query(Job).filter(
        Job.id == job_id,
        Job.user_id == current_user.id
    ).first()

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return {
        "job_id": job.id,
        "status": job.status,
        "mode": job.mode,
        "scope": job.scope,
        "total_emails": job.total_emails,
        "processed_emails": job.processed_emails,
        "error_count": job.error_count,
        "category_counts": job.category_counts or {},
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


@app.post("/api/jobs/{job_id}/cancel")
async def cancel_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    job = db.query(Job).filter(
        Job.id == job_id,
        Job.user_id == current_user.id
    ).first()

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status not in [JobStatus.PENDING, JobStatus.RUNNING]:
        raise HTTPException(status_code=400, detail="Job cannot be cancelled")

    if job.celery_task_id:
        from workers import celery_app
        celery_app.control.revoke(job.celery_task_id, terminate=True)

    job.status = JobStatus.CANCELLED
    db.commit()

    logger.info(f"Cancelled job {job_id}")

    return {"job_id": job_id, "status": job.status}


@app.get("/api/jobs")
async def list_jobs(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = 10,
):
    jobs = (
        db.query(Job)
        .filter(Job.user_id == current_user.id)
        .order_by(Job.created_at.desc())
        .limit(limit)
        .all()
    )

    return [
        {
            "job_id": job.id,
            "status": job.status,
            "mode": job.mode,
            "scope": job.scope,
            "total_emails": job.total_emails,
            "processed_emails": job.processed_emails,
            "error_count": job.error_count,
            "category_counts": job.category_counts or {},
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        }
        for job in jobs
    ]


# Categories routes
@app.get("/api/categories")
async def get_categories(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    categories = db.query(Category).all()
    return [
        {
            "id": cat.id,
            "name": cat.name,
            "color": cat.color,
            "description": cat.description,
            "gmail_label": cat.gmail_label,
        }
        for cat in categories
    ]


# Stats routes
@app.get("/api/stats")
async def get_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    completed_jobs = (
        db.query(Job)
        .filter(
            Job.user_id == current_user.id,
            Job.status == JobStatus.COMPLETED
        )
        .order_by(Job.completed_at.desc())
        .limit(10)
        .all()
    )

    total_processed = sum(job.processed_emails for job in completed_jobs)
    
    last_job = completed_jobs[0] if completed_jobs else None
    last_run_time = last_job.completed_at.isoformat() if last_job and last_job.completed_at else None

    category_totals = {}
    for job in completed_jobs:
        for category, count in (job.category_counts or {}).items():
            category_totals[category] = category_totals.get(category, 0) + count

    return {
        "total_processed": total_processed,
        "last_run_time": last_run_time,
        "category_counts": category_totals,
        "unread_count": 0,  # Would require Gmail API call
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.DEBUG,
    )