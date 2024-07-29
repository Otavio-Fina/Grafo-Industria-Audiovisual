import requests
import sys
from concurrent.futures import ThreadPoolExecutor
import igraph as ig

# Modificar a configuração padrão do Python para UTF-8
sys.stdout.reconfigure(encoding='utf-8')

# Substitua 'sua_chave_api' pela sua chave de API do TMDb
api_key = 'e09c000729271eec3794b6bcd05e460b'
discover_url = 'https://api.themoviedb.org/3/discover/movie'
details_url = 'https://api.themoviedb.org/3/movie'
credits_url = 'https://api.themoviedb.org/3/movie/{}/credits'

# Parâmetros para filtrar os filmes
discover_params = {
    'api_key': api_key,
    'language': 'en-US',
    'region': 'US',
    'sort_by': 'release_date.asc',
    'include_adult': 'false',
    'include_video': 'false',
    'primary_release_year': '2023',
    'with_release_type': '3|2',  # 3 é o lançamento no cinema, 2 é o lançamento digital
    'vote_count.gte': 500
}

contPessoasInvolvidas = 0

def get_movie_details(idFilme):
    movie_url = f"{details_url}/{idFilme}"
    details_params = {
        'api_key': api_key,
        'language': 'en-US'
    }
    response = requests.get(movie_url, params=details_params)
    if response.status_code == 200:
        movie_details = response.json()
        imdb_id = movie_details.get('imdb_id')
        budget = movie_details.get('budget')
        revenue = movie_details.get('revenue')
        title = movie_details.get('title')
        return {
            'imdb_id': imdb_id,
            'budget': budget,
            'revenue': revenue,
            'title': title
        } if imdb_id else None
    else:
        print(f'Erro ao obter detalhes do filme ID {idFilme}: {response.status_code} - {response.text}')
        return None

# Função para obter o elenco do filme
def get_movie_cast(idFilme):
    credits_url_formatted = credits_url.format(idFilme)
    credits_params = {
        'api_key': api_key
    }
    response = requests.get(credits_url_formatted, params=credits_params)
    if response.status_code == 200:
        credits = response.json()
        cast = credits.get('cast', [])
        return cast
    else:
        print(f'Erro ao obter elenco do filme ID {idFilme}: {response.status_code} - {response.text}')
        return []

# Função para buscar filmes e obter IMDb IDs, elenco, orçamento, receita e título
def fetch_imdb_ids_and_cast():
    global contPessoasInvolvidas  # Declare a variável como global
    response = requests.get(discover_url, params=discover_params)
    filmes = ''
    numPags = 0

    if response.status_code == 200:
        filmes = response.json()
        numPags = int(filmes['total_pages'])
        print('Total de páginas:', numPags)
        print('Total de filmes:', filmes['total_results'])
    else:
        print(f'Erro na busca de filmes: {response.status_code} - {response.text}')
        return []

    listaFilmes = []

    if response.status_code == 200:
        for page in range(1, numPags + 1):
            discover_params['page'] = page
            response2 = requests.get(discover_url, params=discover_params)
            if response2.status_code == 200:
                filmesDaPag = response2.json()
                for filmeAtual in filmesDaPag['results']:
                    listaFilmes.append(filmeAtual['id'])
            else:
                print(f'Erro na busca de filmes na página {page}: {response2.status_code} - {response2.text}')

    grafoData = []

    with ThreadPoolExecutor(max_workers=10) as executor:
        movie_details_list = list(executor.map(get_movie_details, listaFilmes))
        cast_lists = list(executor.map(get_movie_cast, listaFilmes))

    for movie_details, cast in zip(movie_details_list, cast_lists):
        if movie_details and movie_details['imdb_id']:
            grafoData.append({
                'imdb_id': movie_details['imdb_id'],
                'title': movie_details['title'],
                'budget': movie_details['budget'],
                'revenue': movie_details['revenue'],
                'cast': [{'name': member['name']} for member in cast]
            })
            contPessoasInvolvidas += len(cast)  # Atualize aqui também

    return grafoData

# Executar a função e imprimir os resultados
grafoData = fetch_imdb_ids_and_cast()

# Construção do grafo
n_vertices = len(grafoData) + contPessoasInvolvidas
qtdePessoasJaAtribuidas = len(grafoData)

# Dicionário para mapear atores aos seus índices no grafo
actor_dict = {}
edges = []
weights = []  # Lista para armazenar os pesos das arestas

# Adicionando vértices e arestas
for i in range(len(grafoData)):
    movie_id = grafoData[i]['imdb_id']
    budget = grafoData[i]['budget']
    for person in grafoData[i]['cast']:
        actor_name = person['name']
        if actor_name not in actor_dict:
            actor_dict[actor_name] = qtdePessoasJaAtribuidas
            qtdePessoasJaAtribuidas += 1
        edges.append((i, actor_dict[actor_name]))
        weights.append(budget)  # Adiciona o budget como peso da aresta

# Criação do grafo
g = ig.Graph(n_vertices, edges)

# Adicionando rótulos aos vértices
g.vs['label'] = [''] * n_vertices
budgets = []
for i in range(len(grafoData)):
    g.vs[i]['label'] = grafoData[i]['title']
    budgets.append(grafoData[i]['budget'])
for actor_name, index in actor_dict.items():
    g.vs[index]['label'] = actor_name

# Normalização dos valores de budget para a faixa de 1 a 20
min_budget = min(budgets)
max_budget = max(budgets)
normalized_sizes = [1 + 19 * (budget - min_budget) / (max_budget - min_budget) for budget in budgets]

# Adicionando tamanhos aos vértices dos filmes
vertex_sizes = [normalized_sizes[i] if i < len(grafoData) else 10 for i in range(n_vertices)]

# Adicionando pesos às arestas
g.es['weight'] = weights

# Exportando o grafo para GraphML
g.write_graphml("grafo_filmes.graphml")

print('Grafo criado e exportado para grafo_filmes.graphml')
