# check that an expert can log in and only view the case list
import os
from werkzeug.security import generate_password_hash
from app import app

def test_expert_is_read_only(monkeypatch):
    app.config['TESTING'] = True
    monkeypatch.setenv('EXPERT_USERNAME', 'reviewer-test')
    monkeypatch.setenv('EXPERT_PASSWORD_HASH', generate_password_hash('test-only-strong-password'))
    with app.test_client() as client:
        assert client.get('/expert/cases').status_code == 302
        login = client.get('/expert/login')
        assert login.status_code == 200
        with client.session_transaction() as sess:
            token = sess['csrf']
        response = client.post('/expert/login', data={'csrf_token': token, 'username': 'reviewer-test', 'password': 'test-only-strong-password'})
        assert response.status_code == 302
        assert '/expert/cases' in response.headers['Location']
        page = client.get('/expert/cases')
        assert page.status_code == 200
        assert 'الحالات'.encode('utf-8') in page.data
        assert client.get('/dashboard').status_code == 302
        assert client.get('/cases/new').status_code == 302
        assert client.get('/profile').status_code == 302
        with client.session_transaction() as sess:
            token = sess['csrf']
        assert client.post('/expert/logout', data={'csrf_token': token}).status_code == 302
        assert client.get('/expert/cases').status_code == 302
