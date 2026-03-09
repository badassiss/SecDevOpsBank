# tests/test_app.py
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'app')))

import pytest
from app import app

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_home_page(client):
    """Test que la page d'accueil charge correctement"""
    response = client.get('/')
    assert response.status_code == 200
    assert b'SecDevOpsBank' in response.data

def test_debug_endpoint(client):
    """Test que l'endpoint debug existe (vulnérable !)"""
    response = client.get('/api/debug')
    assert response.status_code == 200
    assert b'secret_key' in response.data

def test_user_endpoint(client):
    """Test basique de l'endpoint user"""
    response = client.get('/api/user?username=admin')
    assert response.status_code == 200