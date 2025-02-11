from flask import Flask, request, jsonify, render_template, redirect, url_for, session
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from authlib.integrations.flask_client import OAuth
import psycopg2
import os
from models import  Usuario, bcrypt
from config import DATABASE_URL, SECRET_KEY, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET,tmdb
from dotenv import load_dotenv
from tmdbv3api import Movie, TV

# Carrega as variáveis do arquivo .env
load_dotenv()

app = Flask(__name__)

# Converte postgres:// para postgresql:// se necessário
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

app.config["SECRET_KEY"] = SECRET_KEY

# Configuração do Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)

# Configuração do Banco de Dados
conn = psycopg2.connect(DATABASE_URL)
cursor = conn.cursor()

# Configuração do OAuth
oauth = OAuth(app)

google = oauth.register(
    name='google',
    client_id=GOOGLE_CLIENT_ID,
    client_secret=GOOGLE_CLIENT_SECRET,
    authorize_url='https://accounts.google.com/o/oauth2/auth',
    access_token_url='https://oauth2.googleapis.com/token',
    client_kwargs={
        'scope': 'openid email profile',
        'token_endpoint_auth_method': 'client_secret_post',
        'userinfo_endpoint': 'https://openidconnect.googleapis.com/v1/userinfo',
    },
    jwks_uri='https://www.googleapis.com/oauth2/v3/certs'
)

@login_manager.user_loader
def load_user(user_id):
    cursor.execute("SELECT id, nome, email FROM usuario WHERE id = %s", (user_id,))
    user = cursor.fetchone()
    return Usuario(*user) if user else None

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/login/google")
def login_google():
    return google.authorize_redirect("http://127.0.0.1:5000/login/google/callback", prompt="consent")


@app.route("/login/google/callback")
def google_authorized():
    token = google.authorize_access_token()
    if not token:
        return jsonify({"erro": "Falha no login com o Google."}), 400
    
    session['google_token'] = token
    user_info = google.get('https://www.googleapis.com/oauth2/v1/userinfo').json()
    
    cursor.execute("SELECT id FROM usuario WHERE email = %s", (user_info['email'],))
    usuario = cursor.fetchone()
    
    if not usuario:
        cursor.execute("INSERT INTO usuario (nome, email) VALUES (%s, %s) RETURNING id", (user_info['name'], user_info['email']))
        conn.commit()
        usuario = cursor.fetchone()
    
    login_user(Usuario(usuario[0], user_info['name'], user_info['email']))
    return redirect(url_for('filmes'))

@app.route("/cadastro", methods=["POST"])
def cadastrar_usuario():
    dados = request.json
    if not dados or not dados.get("nome") or not dados.get("email") or not dados.get("senha_hash"):
        return jsonify({"erro": "Todos os campos são obrigatórios"}), 400
    
    cursor.execute("SELECT id FROM usuario WHERE email = %s", (dados["email"],))
    if cursor.fetchone():
        return jsonify({"erro": "E-mail já cadastrado"}), 400
    
    cursor.execute("INSERT INTO usuario (nome, email, senha_hash) VALUES (%s, %s, %s)", (dados["nome"], dados["email"], dados["senha_hash"]))
    conn.commit()
    
    return jsonify({"mensagem": "Usuário cadastrado com sucesso!"}), 201

@app.route("/login", methods=["POST"])
def login():
    dados = request.json
    cursor.execute("SELECT id, nome, senha_hash FROM usuario WHERE email = %s", (dados["email"],))
    usuario = cursor.fetchone()
    
    if usuario and usuario[2] == dados["senha_hash"]:
        login_user(Usuario(usuario[0], usuario[1], dados["email"]))
        return jsonify({"mensagem": f"Bem-vindo, {usuario[1]}!"})
    
    return jsonify({"erro": "Credenciais inválidas"}), 401

@app.route("/perfil", methods=["GET"])
@login_required
def perfil():
    return jsonify({"nome": current_user.nome, "email": current_user.email})

@app.route("/logout", methods=["GET"])
@login_required
def logout():
    logout_user()
    return jsonify({"mensagem": "Logout realizado com sucesso!"})

@app.route('/filmes')
def filmes():
    return render_template('filmes.html')

# Conectar ao banco de dados
def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

# Endpoint para buscar detalhes de filmes ou séries
@app.route('/buscar', methods=['GET'])
def buscar_detalhes():
    tipo = request.args.get('tipo')  # 'filme' ou 'serie'
    titulo = request.args.get('titulo')

    if not titulo or tipo not in ['filme', 'serie']:
        return jsonify({'erro': 'Parâmetros inválidos'}), 400

    conn = get_db_connection()
    cur = conn.cursor()

    if tipo == 'filme':
        movie = Movie()
        resultado = movie.search(titulo)
    else:
        tv = TV()
        resultado = tv.search(titulo)

    if resultado:
        detalhes = {
            'titulo': resultado[0].title if tipo == 'filme' else resultado[0].name,
            'descricao': resultado[0].overview,
            'data_lancamento': resultado[0].release_date if tipo == 'filme' else resultado[0].first_air_date
        }

        # Salvar no histórico de buscas
        cur.execute(
            "INSERT INTO historico (titulo, tipo) VALUES (%s, %s)",
            (detalhes['titulo'], tipo)
        )
        conn.commit()
        cur.close()
        conn.close()

        return jsonify(detalhes)

    return jsonify({'erro': 'Nenhum resultado encontrado'}), 404

@app.route('/favoritos/adicionar', methods=['POST'])
def adicionar_favorito():
    try:
        data = request.get_json()  # Obtendo dados JSON da requisição
        print('Dados recebidos:', data)  # Verificando os dados recebidos

        titulo = data.get('titulo')
        tipo = data.get('tipo')
        descricao = data.get('descricao', '')

        if not titulo or tipo not in ['filme', 'serie']:
            print(f"Parâmetros inválidos: {titulo}, {tipo}")  # Debug para identificar o que está errado
            return jsonify({'erro': 'Parâmetros inválidos'}), 400

        # Conectar ao banco de dados
        conn = get_db_connection()
        cur = conn.cursor()

        # Inserir no banco de dados
        cur.execute(
            "INSERT INTO favoritos (titulo, tipo, descricao) VALUES (%s, %s, %s)",
            (titulo, tipo, descricao)
        )
        conn.commit()

        cur.close()
        conn.close()

        return jsonify({'mensagem': 'Favorito adicionado com sucesso!'}), 200

    except Exception as e:
        print('Erro ao adicionar favorito:', e)  # Mostrar o erro detalhado
        return jsonify({'erro': f'Erro ao adicionar favorito: {str(e)}'}), 500




# Endpoint para listar todos os favoritos
@app.route('/favoritos', methods=['GET'])
def listar_favoritos():
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("SELECT id, titulo, tipo, descricao, data_adicao FROM favoritos ORDER BY data_adicao DESC")
    favoritos = cur.fetchall()
    
    cur.close()
    conn.close()

    resultado = [
        {
            'id': fav[0],
            'titulo': fav[1],
            'tipo': fav[2],
            'descricao': fav[3],
            'data_adicao': fav[4].strftime('%Y-%m-%d %H:%M:%S')
        }
        for fav in favoritos
    ]

    return jsonify(resultado)
# Endpoint para apagar um favorito
@app.route('/favoritos/<int:id>', methods=['DELETE'])
def remover_favorito(id):
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Exclui o favorito com o ID especificado
    cur.execute("DELETE FROM favoritos WHERE id = %s", (id,))
    conn.commit()

    cur.close()
    conn.close()

    return jsonify({"message": "Favorito removido com sucesso!"}), 200


# Endpoint para listar o histórico de buscas
@app.route('/historico', methods=['GET'])
def listar_historico():
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT titulo, tipo FROM historico ORDER BY data_busca DESC")
    historico = cur.fetchall()

    cur.close()
    conn.close()

    resultado = [
        {
            'titulo': item[0],
            'tipo': item[1]
        }
        for item in historico
    ]

    return jsonify(resultado)

@app.route('/historico/apagar', methods=['DELETE'])
@login_required
def apagar_historico():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM historico")
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"mensagem": "Histórico apagado com sucesso!"}), 200
    except Exception as e:
        return jsonify({"erro": f"Erro ao apagar histórico: {str(e)}"}), 500

@app.route('/favoritos/apagar/<int:id>', methods=['DELETE'])
@login_required
def apagar_favorito(id):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM favoritos WHERE id = %s", (id,))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"mensagem": "Favorito apagado com sucesso!"}), 200
    except Exception as e:
        return jsonify({"erro": f"Erro ao apagar favorito: {str(e)}"}), 500


# Rodar o servidor Flask
if __name__ == '__main__':
    app.run(debug=True)
