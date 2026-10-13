# Photography

This project is a Flask application with server-rendered templates, account management, and photography bookings.

## Python dependencies

Install the dependencies with `python -m pip install -r requirements.txt`.

The application uses PyMySQL directly instead of Flask-MySQLdb. Keeping Flask-MySQLdb installed would still pull in its `mysqlclient` dependency, even if PyMySQL were installed alongside it. PyMySQL avoids the MySQL/MariaDB development libraries required to compile `mysqlclient`.

The existing database configuration names (`DB_HOST`, `DB_USER`, `DB_PASSWORD`, and `DB_NAME`) and SQL queries were retained. Connections are opened only when needed, use dictionary cursors, and are closed when the Flask application context ends. Database writes still require explicit commits.

## Netlify deployment limitation

Removing the native database dependency addresses the dependency-installation error only. It does not turn the Flask application into a static site or provide a Flask runtime on Netlify. The files in `templates/` require Flask to render them and should not be published directly as static HTML.

A functional Netlify deployment requires a separate migration of the server-rendered pages and backend routes to a supported frontend and Netlify Functions. Persistent application data for that migration should use Netlify Database. No frontend, backend-runtime, or database migration is included in this dependency fix.
