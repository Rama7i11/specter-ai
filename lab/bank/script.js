document.addEventListener('DOMContentLoaded', function () {
  var form = document.querySelector('form');
  var btn  = document.querySelector('.login-btn');

  if (form && btn) {
    form.addEventListener('submit', function () {
      btn.textContent = 'Signing in...';
      btn.disabled    = true;
      btn.style.opacity = '0.7';
    });
  }
});
