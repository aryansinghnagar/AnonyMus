function toggleView(viewId) {
  document.getElementById('login-view').style.display = viewId === 'login-view' ? 'block' : 'none';
  document.getElementById('register-view').style.display = viewId === 'register-view' ? 'block' : 'none';
  document.getElementById('login-error').innerText = '';
  document.getElementById('reg-error').innerText = '';
  document.getElementById('reg-success').innerText = '';
}

async function loginUser() {
  const u = document.getElementById('login-username').value.trim();
  const p = document.getElementById('login-password').value.trim();
  if (!u || !p) return;

  const res = await fetch('/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: u, password: p })
  });
  const data = await res.json();
  if (data.success) {
    window.location.href = '/chat';
  } else {
    document.getElementById('login-error').innerText = data.error || 'Login failed';
  }
}

async function registerUser() {
  const u = document.getElementById('reg-username').value.trim();
  const p = document.getElementById('reg-password').value.trim();
  if (!u || !p) return;

  const res = await fetch('/register', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: u, password: p })
  });
  const data = await res.json();
  if (data.success) {
    document.getElementById('reg-success').innerText = 'Registration successful! You can now log in.';
    document.getElementById('reg-error').innerText = '';
    setTimeout(() => toggleView('login-view'), 1500);
  } else {
    document.getElementById('reg-error').innerText = data.error || 'Registration failed';
    document.getElementById('reg-success').innerText = '';
  }
}

document.addEventListener('DOMContentLoaded', () => {
  const btnLogin = document.getElementById('btn-login');
  if (btnLogin) btnLogin.addEventListener('click', loginUser);

  const btnReg = document.getElementById('btn-register');
  if (btnReg) btnReg.addEventListener('click', registerUser);

  const toReg = document.getElementById('link-to-register');
  if (toReg) toReg.addEventListener('click', () => toggleView('register-view'));

  const toLogin = document.getElementById('link-to-login');
  if (toLogin) toLogin.addEventListener('click', () => toggleView('login-view'));
});
