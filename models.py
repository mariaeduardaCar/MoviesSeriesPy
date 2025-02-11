import psycopg2
from flask_bcrypt import Bcrypt
from flask_login import UserMixin
import os
from config import DATABASE_URL

bcrypt = Bcrypt()

# Conexão com o Banco de Dados
conn = psycopg2.connect(DATABASE_URL)
cursor = conn.cursor()

class Usuario(UserMixin):
    def __init__(self, id, nome, email, senha_hash=None):
        self.id = id
        self.nome = nome
        self.email = email
        self.senha_hash = senha_hash

    def set_senha(self, senha):
        self.senha_hash = bcrypt.generate_password_hash(senha).decode("utf-8")
        cursor.execute("UPDATE usuarios SET senha = %s WHERE id = %s", (self.senha_hash, self.id))
        conn.commit()

    def verificar_senha(self, senha):
        return bcrypt.check_password_hash(self.senha_hash, senha)
