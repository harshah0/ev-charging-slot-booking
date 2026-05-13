from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy.exc import IntegrityError

from extensions import db
from models import User
from utils.auth_validation import (
	is_safe_next_url,
	validate_login_data,
	validate_registration_data,
)
from utils.csrf import generate_csrf_token, validate_csrf_token

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


@auth_bp.app_context_processor
def inject_auth_helpers():
	return {"csrf_token": generate_csrf_token}


@auth_bp.get("/register")
def register():
	if current_user.is_authenticated:
		return redirect(url_for("dashboard.entry"))
	return render_template("auth/register.html")


@auth_bp.post("/register")
def register_post():
	if current_user.is_authenticated:
		return redirect(url_for("dashboard.entry"))

	if not validate_csrf_token(request.form.get("csrf_token")):
		flash("Your session has expired. Please try again.", "danger")
		return redirect(url_for("auth.register"))

	username = request.form.get("username", "")
	email = request.form.get("email", "")
	password = request.form.get("password", "")
	confirm_password = request.form.get("confirm_password", "")

	errors = validate_registration_data(username, email, password, confirm_password)
	if errors:
		for error in errors:
			flash(error, "danger")
		return render_template("auth/register.html", form=request.form), 400

	existing_user = User.query.filter(
		(User.username == username.strip()) | (User.email == email.strip().lower())
	).first()
	if existing_user:
		flash("A user with that username or email already exists.", "danger")
		return render_template("auth/register.html", form=request.form), 409

	user = User(username=username.strip(), email=email.strip().lower())
	user.set_password(password)

	try:
		db.session.add(user)
		db.session.commit()
	except IntegrityError:
		db.session.rollback()
		flash("Unable to create your account right now.", "danger")
		return render_template("auth/register.html", form=request.form), 409

	login_user(user)
	session.permanent = True
	flash("Account created successfully.", "success")
	return redirect(url_for("dashboard.entry"))


@auth_bp.get("/login")
def login():
	if current_user.is_authenticated:
		return redirect(url_for("dashboard.entry"))
	return render_template("auth/login.html")


@auth_bp.post("/login")
def login_post():
	if current_user.is_authenticated:
		return redirect(url_for("dashboard.entry"))

	if not validate_csrf_token(request.form.get("csrf_token")):
		flash("Your session has expired. Please try again.", "danger")
		return redirect(url_for("auth.login"))

	email = request.form.get("email", "")
	password = request.form.get("password", "")

	errors = validate_login_data(email, password)
	if errors:
		for error in errors:
			flash(error, "danger")
		return render_template("auth/login.html", form=request.form), 400

	user = User.query.filter_by(email=email.strip().lower()).first()
	if not user or not user.check_password(password):
		flash("Invalid email or password.", "danger")
		return render_template("auth/login.html", form=request.form), 401

	login_user(user)
	session.permanent = True
	next_url = request.form.get("next") or request.args.get("next")
	if is_safe_next_url(next_url):
		return redirect(next_url)

	flash("Logged in successfully.", "success")
	return redirect(url_for("dashboard.entry"))


@auth_bp.post("/logout")
@login_required
def logout():
	if not validate_csrf_token(request.form.get("csrf_token")):
		flash("Your session has expired. Please try again.", "danger")
		return redirect(url_for("home.home"))

	logout_user()
	session.pop("csrf_token", None)
	flash("You have been logged out.", "info")
	return redirect(url_for("home.home"))
