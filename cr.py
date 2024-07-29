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

# Mapeamento de países para idiomas principais
countries_languages = {
    'US': 'en',
    'IN': 'hi',
    'CN': 'zh',
    'JP': 'ja',
    'GB': 'en'
}

# Parâmetros comuns para filtrar os filmes
common_params = {
    'api_key': api_key,
    'sort_by': 'vote_count.desc',
    'include_adult': 'false',
    'include_video': 'false',
    'primary_release_year': '2023',
    'vote_count.gte': 5  # Ajuste para filmes com pelo menos 5 votos
}

def get_movie_details(idFilme):
    movie_url = f"{details_url}/{idFilme}"
    details_params = {
        'api_key': api_key
    }
    response = requests.get(movie_url, params=details_params)
    if response.status_code == 200:
        movie_details = response.json()
        imdb_id = movie_details.get('imdb_id')
        budget = movie_details.get('budget')
        revenue = movie_details.get('revenue')
        title = movie_details.get('title')
        production_countries = [country['name'] for country in movie_details.get('production_countries', [])]
        return {
            'imdb_id': imdb_id,
            'budget': budget,
            'revenue': revenue,
            'title': title,
            'production_countries': production_countries,
            'vote_count': movie_details.get('vote_count')
        } if imdb_id else None
    else:
        print(f'Erro ao obter detalhes do filme ID {idFilme}: {response.status_code} - {response.text}')
        return None

# Função para buscar filmes e obter IMDb IDs, orçamento, receita, título e países de produção
def fetch_movies_by_country(country, language):
    country_params = common_params.copy()
    country_params['with_original_language'] = language
    country_params['region'] = country

    response = requests.get(discover_url, params=country_params)
    filmes = ''
    numPags = 0

    if response.status_code == 200:
        filmes = response.json()
        numPags = min(int(filmes['total_pages']), 10)  # Limitar a busca a 10 páginas para evitar muitos resultados
        print(f'Total de páginas para {country}:', numPags)
        print(f'Total de filmes para {country}:', filmes['total_results'])
    else:
        print(f'Erro na busca de filmes: {response.status_code} - {response.text}')
        return []

    listaFilmes = []

    for page in range(1, numPags + 1):
        country_params['page'] = page
        response2 = requests.get(discover_url, params=country_params)
        if response2.status_code == 200:
            filmesDaPag = response2.json()
            for filmeAtual in filmesDaPag['results']:
                listaFilmes.append(filmeAtual['id'])
        else:
            print(f'Erro na busca de filmes na página {page}: {response2.status_code} - {response2.text}')

    grafoData = []

    with ThreadPoolExecutor(max_workers=10) as executor:
        movie_details_list = list(executor.map(get_movie_details, listaFilmes))

    for movie_details in movie_details_list:
        if movie_details and movie_details['imdb_id']:
            grafoData.append(movie_details)

    # Pegar os 100 filmes com mais votos de cada país
    sorted_movies = sorted(grafoData, key=lambda x: x['vote_count'], reverse=True)[:100]

    return sorted_movies

# Executar a função para cada país e combinar os resultados
all_grafoData = []
country_grafos = {}
for country, language in countries_languages.items():
    country_grafoData = fetch_movies_by_country(country, language)
    all_grafoData.extend(country_grafoData)
    country_grafos[country] = country_grafoData

# Construção do grafo completo
n_vertices = len(all_grafoData)
movie_dict = {all_grafoData[i]['imdb_id']: i for i in range(n_vertices)}
edges = []

for i in range(n_vertices):
    for j in range(i + 1, n_vertices):
        common_countries = set(all_grafoData[i]['production_countries']).intersection(set(all_grafoData[j]['production_countries']))
        if common_countries:
            edges.append((i, j))

g = ig.Graph(n_vertices, edges)
g.vs['label'] = [movie['title'] for movie in all_grafoData]

budgets = [movie['budget'] for movie in all_grafoData]
min_budget = min(budgets) if budgets else 0
max_budget = max(budgets) if budgets else 1
normalized_sizes = [1 + 59 * (budget - min_budget) / (max_budget - min_budget) for budget in budgets]
scaled_sizes = [((int(size) // 10) * 10) for size in normalized_sizes]
g.vs['size'] = scaled_sizes

def prim_mst(graph):
    mst = graph.spanning_tree(weights=None, return_tree=True)
    return mst

# Executar o algoritmo de Prim no grafo principal e atualizar o grafo
mst = prim_mst(g)
g = mst
g.write_graphml("grafo_filmes_mst.graphml")
print('Grafo mínimo gerador criado e exportado para grafo_filmes_mst.graphml')

# Criação e exportação de subgrafos para cada país
for country, grafoData in country_grafos.items():
    country_vertices = [movie_dict[movie['imdb_id']] for movie in grafoData if movie['imdb_id'] in movie_dict]
    subgraph = g.subgraph(country_vertices)
    
    # Construção das arestas do subgrafo
    subgraph_edges = []
    for i in range(len(country_vertices)):
        for j in range(i + 1, len(country_vertices)):
            common_countries = set(grafoData[i]['production_countries']).intersection(set(grafoData[j]['production_countries']))
            if common_countries:
                subgraph_edges.append((i, j))

    country_g = ig.Graph(len(country_vertices), subgraph_edges)
    country_g.vs['label'] = [grafoData[i]['title'] for i in range(len(country_vertices))]
    country_g.vs['size'] = [scaled_sizes[movie_dict[grafoData[i]['imdb_id']]] for i in range(len(country_vertices))]

    # Executar o algoritmo de Prim no subgrafo
    country_mst = prim_mst(country_g)
    country_mst.write_graphml(f"grafo_filmes_{country}_mst.graphml")
    print(f'Grafo mínimo gerador para {country} criado e exportado para grafo_filmes_{country}_mst.graphml')
