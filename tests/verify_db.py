import sys
import os
sys.path.append(os.getcwd())

from app.core.database import Base, engine, SessionLocal
from app.models.orm import User, Project, Generation

def verify():
    print("Creating tables...")
    Base.metadata.create_all(bind=engine)
    print("Tables created.")

    db = SessionLocal()
    try:
        # Create User
        print("Creating test user...")
        user_id = "test-user-1"
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            user = User(id=user_id, email="test@example.com", display_name="Test User")
            db.add(user)
            db.commit()
        print(f"User created: {user.id}")

        # Create Project
        print("Creating test project...")
        proj = Project(
            title="My Plushie",
            user_id=user_id,
            description="A test project",
            status="concept"
        )
        db.add(proj)
        db.commit()
        print(f"Project created: {proj.id}")

        # Create Generation
        print("Creating test generation job...")
        gen = Generation(
            project_id=proj.id,
            type="text_to_3d",
            status="pending",
            input_params={"prompt": "cute cat"}
        )
        db.add(gen)
        db.commit()
        print(f"Generation job created: {gen.id}")

        # Verify
        p = db.query(Project).filter(Project.id == proj.id).first()
        g = db.query(Generation).filter(Generation.id == gen.id).first()
        
        assert p is not None
        assert g is not None
        assert g.project_id == p.id
        print("✅ Verification SUCCESS: Data persisted correctly.")

    except Exception as e:
        print(f"❌ Verification FAILED: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    verify()
