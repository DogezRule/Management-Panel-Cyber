from app import create_app
from app.extensions import db
from app.models import User

app = create_app()

with app.app_context():
    email = "admin"   # CHANGE THIS to the user you want to delete

    user = User.query.filter_by(email=email).first()
    if not user:
        print(f"No user found with email {email}")
    else:
        db.session.delete(user)
        db.session.commit()
        print(f"User {email} deleted successfully!")
