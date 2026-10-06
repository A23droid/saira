import os
from dotenv import load_dotenv
load_dotenv('.env')
print('ENV:', os.getenv('DATABASE_URL'))
