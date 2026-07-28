import urllib.request
import urllib.parse
import http.cookiejar
import re

# Set up cookie handling (to maintain session)
cookie_jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))

# Step 1: Get the signup page to extract CSRF token
response = opener.open("http://127.0.0.1:8000/accounts/signup/")
html = response.read().decode("utf-8")

# Extract CSRF token from the hidden input field
match = re.search(r'<input[^>]*name="csrfmiddlewaretoken"[^>]*value="([^"]+)"', html)
if match:
    csrf_token = match.group(1)
    print("CSRF Token: " + csrf_token[:20] + "...")
else:
    print("ERROR: Could not find CSRF token")
    exit(1)

# Step 2: Submit the signup form
form_data = {
    "csrfmiddlewaretoken": csrf_token,
    "full_name": "Jane Farmer",
    "email": "jane@example.com",
    "phone_number": "+1234567890",
    "password1": "StrongPass123!",
    "password2": "StrongPass123!",
}

encoded_data = urllib.parse.urlencode(form_data).encode("utf-8")
response = opener.open(
    "http://127.0.0.1:8000/accounts/signup/",
    data=encoded_data
)
html = response.read().decode("utf-8")
print("Status Code: " + str(response.getcode()))
print("Final URL: " + response.geturl())

# Check if we got redirected (success) or stayed on signup page (form validation error)
success_found = "successfully" in html.lower()
print("Success message found: " + str(success_found))

# Show page title
title_match = re.search(r"<title>(.*?)</title>", html)
if title_match:
    print("Page Title: " + title_match.group(1))

if success_found:
    print("\n=== SIGNUP TEST PASSED ===")
else:
    # Check for form errors
    error_match = re.search(r'<div class="invalid-feedback d-block">(.*?)</div>', html, re.DOTALL)
    if error_match:
        print("\nForm Error: " + error_match.group(1).strip())
    print("\n=== SIGNUP TEST FAILED ===")
