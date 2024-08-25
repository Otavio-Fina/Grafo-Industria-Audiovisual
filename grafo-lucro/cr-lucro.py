import requests
import sys
from concurrent.futures import ThreadPoolExecutor
import igraph as ig
import os

# Modificar a configuração padrão do Python para UTF-8
sys.stdout.reconfigure(encoding='utf-8')

# Substitua 'sua_chave_api' pela sua chave de API do TMDb
api_key = 'e09c000729271eec3794b6bcd05e460b'
discover_url = 'https://api.themoviedb.org/3/discover/movie'
details_url = 'https://api.themoviedb.org/3/movie'

# Mapeamento dos principais países da indústria cinematográfica
countries = ['US', 'IN', 'CN', 'JP', 'FR']

# Parâmetros comuns para filtrar os filmes
common_params = {
    'api_key': api_key,
    'sort_by': 'vote_count.desc',
    'include_adult': 'false',
    'include_video': 'false',
    'primary_release_date.gte': '2000-01-01',
    'primary_release_date.lte': '2023-12-31',
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
        budget = movie_details.get('budget', 0)
        revenue = movie_details.get('revenue', 0)
        title = movie_details.get('title')
        production_countries = [country['name'] for country in movie_details.get('production_countries', [])]
        return {
            'imdb_id': imdb_id,
            'budget': budget,
            'revenue': revenue,
            'title': title,
            'production_countries': production_countries,
            'vote_count': movie_details.get('vote_count', 0)
        } if imdb_id else None
    else:
        print(f'Erro ao obter detalhes do filme ID {idFilme}: {response.status_code} - {response.text}')
        return None

def fetch_movies_by_country(country):
    country_params = common_params.copy()
    country_params['with_origin_country'] = country

    response = requests.get(discover_url, params=country_params)
    if response.status_code == 200:
        filmes = response.json()
        numPags = min(int(filmes['total_pages']), 10)
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
            if 'results' in filmesDaPag:
                listaFilmes.extend(filme['id'] for filme in filmesDaPag['results'])
            else:
                print(f'Erro na resposta da página {page}: "results" não encontrado')
        else:
            print(f'Erro na busca de filmes na página {page}: {response2.status_code} - {response2.text}')

    grafoData = []

    with ThreadPoolExecutor(max_workers=10) as executor:
        movie_details_list = list(executor.map(get_movie_details, listaFilmes))

    for movie_details in movie_details_list:
        if movie_details and movie_details['imdb_id']:
            grafoData.append(movie_details)

    sorted_movies = sorted(grafoData, key=lambda x: x['vote_count'], reverse=True)[:250]

    return sorted_movies

def assign_weights_and_labels(graph):
    weights = []
    labels = []
    for edge in graph.es:
        source, target = edge.tuple
        source_degree = graph.degree(source)
        target_degree = graph.degree(target)
        
        # Atribuir o lucro com base no vértice de menor grau
        if source_degree < target_degree:
            weight = graph.vs[source]['revenue']
        elif target_degree < source_degree:
            weight = graph.vs[target]['revenue']
        else:  # Se ambos têm o mesmo grau
            weight = graph.vs[target]['revenue']

        weights.append(weight)
        
        # Definir o rótulo "NE" se o peso for 1
        if weight == 1:
            labels.append("NE")
        else:
            formatted_weight = format_revenue(weight)
            labels.append(formatted_weight)
        
    graph.es['weight'] = weights
    graph.es['label'] = labels

def format_revenue(revenue):
    if revenue >= 1_000_000_000:
        return f"{revenue // 1_000_000_000}B"
    elif revenue >= 1_000_000:
        return f"{revenue // 1_000_000}M"
    elif revenue >= 1_000:
        return f"{revenue // 1_000}k"
    else:
        return str(revenue)

# Caminho do diretório onde o script está localizado
script_directory = os.path.dirname(os.path.abspath(__file__))

# Executar a função para cada país e combinar os resultados
country_grafos = {}
for country in countries:
    country_grafoData = fetch_movies_by_country(country)
    
    n_vertices = len(country_grafoData)
    if n_vertices == 0:
        continue
    
    movie_dict = {country_grafoData[i]['imdb_id']: i for i in range(n_vertices)}
    edges = []

    for i in range(n_vertices):
        for j in range(i + 1, n_vertices):
            common_countries = set(country_grafoData[i]['production_countries']).intersection(set(country_grafoData[j]['production_countries']))
            if common_countries:
                edges.append((i, j))

    if edges:
        g = ig.Graph(n_vertices, edges)
        g.vs['label'] = [movie['title'] for movie in country_grafoData]

        revenues = [movie['revenue'] if movie['revenue'] > 0 else 1 for movie in country_grafoData]
        g.vs['revenue'] = revenues

        min_revenue = min(revenues)
        max_revenue = max(revenues)
        normalized_sizes = [1 + 59 * (revenue - min_revenue) / (max_revenue - min_revenue) for revenue in revenues]
        scaled_sizes = [((int(size) // 10) * 10) for size in normalized_sizes]
        g.vs['size'] = scaled_sizes

        # Executar o algoritmo de Prim para encontrar a árvore geradora mínima (MST)
        mst = g.spanning_tree(weights=None, return_tree=True)
        assign_weights_and_labels(mst)

        # Adicionar aresta de loop no vértice de maior grau
        max_degree_vertex = max(g.vs, key=lambda v: g.degree(v.index))
        max_revenue = max_degree_vertex['revenue']
        mst.add_edge(max_degree_vertex.index, max_degree_vertex.index, weight=max_revenue, label=format_revenue(max_revenue))

        # Nome do arquivo com sufixo "-lucro"
        file_name = f"grafo_filmes_{country}_lucro.graphml"
        file_path = os.path.join(script_directory, file_name)

        mst.write_graphml(file_path)
        print(f'Grafo mínimo gerador para {country} criado e exportado para {file_path}')

print('Processamento concluído.')
