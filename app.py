from flask import Flask, request, flash, render_template

app = Flask(__name__)
app.secret_key = 'testkey'

USERS = {
    "admin@gmail.com": "admin123"
}

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('email')
        password = request.form.get('password')

        if username in USERS and USERS[username] == password:
            flash(f"Welcome, {username}!", 'success')
            return "Login Successful"
        else:
            flash('Invalid username or password.', 'danger')

    return render_template('login.html')


if __name__ == '__main__':
    app.run(debug=True)