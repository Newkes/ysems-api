
start /min "MongoDB" mongod --dbpath ./data/db

timeout /t 3
python manage.py makemigrations
python manage.py migrate
python manage.py runserver
