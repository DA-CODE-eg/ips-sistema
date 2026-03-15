import os
from dotenv import load_dotenv
load_dotenv()

from app import create_app

app = create_app()

@app.route('/ping')
def ping():
    return 'ok', 200

if __name__ == '__main__':
    app.run()
