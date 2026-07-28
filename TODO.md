# Task Progress

- [x] Analyze the issue — password eye icon is slightly above center in password fields
- [x] Read relevant files (auth.css, login.html, signup.html)
- [x] Identify the cause: `top: 50%; transform: translateY(-50%)` is less reliable when the button has its own padding/height
- [x] Apply fix: Replace with `top: 0; bottom: 0; margin: auto 0; height: fit-content;` for robust vertical centering
- [x] Verify fix by reloading login page
- [x] Create superuser "David 123"

