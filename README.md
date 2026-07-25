# Black Diamond 

Cross-platform Secure Escrow System utilizing a Telegram Bot and Web Interface.


<img width="452" height="640" alt="photo_2026-07-25_23-24-18" src="https://github.com/user-attachments/assets/5bc7ce0b-5fdc-4662-bddf-87eebd447266" />

---

## About The Project

Black Diamond is a fault-tolerant escrow service designed to secure peer-to-peer (P2P) transactions between buyers and sellers. The system addresses trust issues in online commerce by offering a transparent, mobile-accessible, and secure mechanism for holding funds until transaction terms are fulfilled.

The platform combines two equal-privilege user interfaces:
* Telegram Bot: Designed for quick actions, notifications, status tracking, and mobile workflows.
* Web Interface: Provides deal details, transaction status validation, and secure payout withdrawals for sellers.
* Shared Core: A centralized backend containing business logic, database operations, and security validation rules shared across both interfaces.

---

## Key Features

* Full Escrow Lifecycle: Deal Creation -> Buyer Join -> Escrow Deposit -> Delivery Confirmation -> Funds Withdrawal.
* Blockchain Integration: Native support for TON (TON Blockchain via tonsdk). The architecture is prepared for USDT TRC-20 support in version 2.0.
* Zero Trust Security Architecture: Strict server-side authorization checks for every action based on user roles (buyer/seller) and valid deal states.
* Cryptographic Data Protection: HMAC-signed Telegram callback data, parametrized SQL queries to prevent SQL injections, and input sanitization against XSS attacks.
* Automated Fee Calculation: Configurable commission rate (COMMISSION_RATE) with clear calculation of net amounts payable to sellers.

---

## Project Structure

```text
BlackDiamond/
├── bot/                # Telegram Handler Layer (aiogram 2.x, FSM workflows)
├── web/                # Web Interface Layer (Flask, REST API, routing)
├── shared/             # Shared Core (Business logic, DB models, payments, notifications)
│   ├── config.py       # Global configuration parameters
│   ├── database.py     # SQLite operations with parametrized queries
│   └── services/       # Payment gateways (TON), cryptography, notifications
├── templates/          # HTML templates for Web interface (Jinja2)
├── static/             # Static web assets (CSS, JS)
├── tests/              # Unit test suite (pytest)
├── run.py              # Main application entry point
└── requirements.txt    # Project dependencies

