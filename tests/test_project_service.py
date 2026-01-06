from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models.orm import Base
from app.services.project_service import ProjectService
from app.models.schemas import ProjectCreate

# 使用内存数据库进行测试
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)

def test_project_service():
    db = TestingSessionLocal()
    service = ProjectService(db)
    
    # 测试创建项目
    create_data = ProjectCreate(title="Test Project", description="Testing service layer", is_public=True)
    project = service.create_project(create_data, "test-user-id")
    
    assert project.title == "Test Project"
    assert project.user_id == "test-user-id"
    print("✅ Create Project OK")
    
    # 测试获取项目列表
    projects = service.get_user_projects("test-user-id")
    assert len(projects) == 1
    assert projects[0].id == project.id
    print("✅ List Projects OK")
    
    # 测试获取单个项目
    fetched_project = service.get_project(project.id, "test-user-id")
    assert fetched_project is not None
    assert fetched_project.title == "Test Project"
    print("✅ Get Project OK")
    
    db.close()

if __name__ == "__main__":
    test_project_service()
