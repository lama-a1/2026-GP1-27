# check the available templates and the public home page
from app import app

def test_case_detail_template_removed():
    assert 'case.html' not in app.jinja_loader.list_templates()

def test_public_home_still_available():
    with app.test_client() as client:
        assert client.get('/').status_code == 200
