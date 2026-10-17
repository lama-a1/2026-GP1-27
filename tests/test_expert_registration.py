import uuid
from app import app


def test_expert_registration_requires_authorization(monkeypatch):
    app.config['TESTING'] = True
    monkeypatch.setenv('EXPERT_REGISTRATION_CODE', 'test-only-authorized-registration-code-12345')
    username = 'reviewer_' + uuid.uuid4().hex[:12]
    with app.test_client() as client:
        page = client.get('/expert/register')
        assert page.status_code == 200
        with client.session_transaction() as sess:
            token = sess['csrf']
        fields = {'csrf_token': token, 'full_name': 'Test Expert', 'username': username,
                  'password': 'strong-test-password-123', 'confirm_password': 'strong-test-password-123'}
        response = client.post('/expert/register', data={**fields, 'authorization_code': 'wrong-code'})
        assert response.status_code == 200
        response = client.post('/expert/register', data={**fields, 'authorization_code': 'test-only-authorized-registration-code-12345'})
        assert response.status_code == 302
        assert '/expert/login' in response.headers['Location']
        response = client.post('/expert/login', data={'csrf_token': token, 'username': username, 'password': 'strong-test-password-123'})
        assert response.status_code == 302
        assert '/expert/cases' in response.headers['Location']
        assert client.get('/expert/cases').status_code == 200
        assert client.get('/cases/new').status_code == 302


def test_public_landing_removed():
    with app.test_client() as client:
        response = client.get('/')
        assert response.status_code == 302
        assert '/login' in response.headers['Location']
