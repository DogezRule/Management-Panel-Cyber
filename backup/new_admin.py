from app import create_app
from app.extensions import db
from app.models import User
from app.security import hash_password

app = create_app()

with app.app_context():
    email = "admin"
    password = "admin"
    
    # Check if the user already exists
    existing = User.query.filter_by(email=email).first()
    if existing:
        print("User already exists.")
    else:
        admin = User(
            email=email,
            password_hash=hash_password(password),
            role="admin",
            is_active=True
        )
        db.session.add(admin)
        db.session.commit()
        print("Admin user created successfully!")
        print(f"Email: {email}")
        print(f"Password: {password}")
