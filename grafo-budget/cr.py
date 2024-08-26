import requests
import sys
from concurrent.futures import ThreadPoolExecutor
import igraph as ig
import os
from collections import defaultdict

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
        duration = movie_details.get('runtime', 0)
        popularity = movie_details.get('popularity', 0)
        release_year = int(movie_details.get('release_date', '1900-01-01').split('-')[0])
        genres = [genre['name'] for genre in movie_details.get('genres', [])]
        vote_count = movie_details.get('vote_count', 0)
        vote_average = movie_details.get('vote_average', 0)  # Garantir que vote_average seja capturado

        return {
            'imdb_id': imdb_id,
            'budget': budget,
            'revenue': revenue,
            'title': title,
            'production_countries': production_countries,
            'vote_count': vote_count,
            'vote_average': vote_average,  # Incluindo vote_average no retorno
            'duration': duration,
            'popularity': popularity,
            'release_year': release_year,
            'genres': genres
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
    else:
        print(f'Erro na busca de filmes: {response.status_code} - {response.text}')
        return [], defaultdict(lambda: {'budget': 0, 'revenue': 0})

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
    genre_stats = defaultdict(lambda: {'budget': 0, 'revenue': 0})

    with ThreadPoolExecutor(max_workers=10) as executor:
        movie_details_list = list(executor.map(get_movie_details, listaFilmes))

    for movie_details in movie_details_list:
        if movie_details and movie_details['imdb_id']:
            grafoData.append(movie_details)
            for genre in movie_details['genres']:
                genre_stats[genre]['budget'] += movie_details['budget']
                genre_stats[genre]['revenue'] += movie_details['revenue']


    total_filmes = len(grafoData)
    total_budget = sum(movie['budget'] for movie in grafoData)
    total_revenue = sum(movie['revenue'] for movie in grafoData)
    avg_duration = sum(movie['duration'] for movie in grafoData) / total_filmes if total_filmes else 0
    avg_popularity = sum(movie['popularity'] for movie in grafoData) / total_filmes if total_filmes else 0
    avg_release_year = sum(movie['release_year'] for movie in grafoData) / total_filmes if total_filmes else 0
    
    # Cálculo da média das notas dos filmes
    notas_filmes = [movie.get('vote_average', 0) for movie in grafoData if movie.get('vote_count', 0) > 0]
    avg_rating = sum(notas_filmes) / len(notas_filmes) if notas_filmes else 0

    # Impressão dos resultados
    print("\n\n\n=========================================\n\n\n")
    print(f"\nPaís: {country}")
    print(f"Total de Filmes: {total_filmes}")
    print(f"Soma do Orçamento dos Filmes: {format_currency(total_budget)}")
    print(f"Soma do Lucro dos Filmes: {format_currency(total_revenue)}")
    print(f"Média de Duração dos Filmes: {avg_duration:.2f} minutos")
    print(f"Média de Popularidade: {avg_popularity:.2f}")
    print(f"Média de Ano de Lançamento: {avg_release_year:.2f}")
    
    # Impressão da média das notas
    print(f"Média de Notas dos Filmes: {avg_rating:.2f}")
    # Exibir informações de orçamento e lucro por gênero
    print("\nEstatísticas por Gênero:")
    for genre, stats in genre_stats.items():
        print(f"Gênero: {genre}")
        print(f"Soma do Orçamento: {format_currency(stats['budget'])}")
        print(f"Soma do Lucro: {format_currency(stats['revenue'])}")

    return grafoData, genre_stats

def assign_weights_and_labels(graph, weight_attr='budget'):
    weights = []
    labels = []
    for edge in graph.es:
        source, target = edge.tuple
        if weight_attr in graph.vs.attributes():
            source_degree = graph.degree(source)
            target_degree = graph.degree(target)
            
            # Atribuir o orçamento com base no vértice de menor grau
            if source_degree < target_degree:
                weight = graph.vs[source][weight_attr]
            elif target_degree < source_degree:
                weight = graph.vs[target][weight_attr]
            else:  # Se ambos têm o mesmo grau
                weight = graph.vs[target][weight_attr]

            weights.append(weight)
            
            # Formatar o peso como rótulo
            formatted_weight = format_currency(weight)
            labels.append(formatted_weight)
        else:
            print(f"Erro: Atributo '{weight_attr}' não encontrado nos vértices do grafo.")
            return

    graph.es['weight'] = weights
    graph.es['label'] = labels

def format_currency(value):
    if value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.2f}B"
    elif value >= 1_000_000:
        return f"{value / 1_000_000:.2f}M"
    elif value >= 1_000:
        return f"{value / 1_000:.2f}k"
    else:
        return str(value)

# Caminho do diretório onde o script está localizado
script_directory = os.path.dirname(os.path.abspath(__file__))

all_movies_data = []
all_mst_edges = []

# Executar a função para cada país e combinar os resultados
for country in countries:
    country_grafoData, genre_stats = fetch_movies_by_country(country)
    
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

        budgets = [movie['budget'] if movie['budget'] > 0 else 1 for movie in country_grafoData]
        g.vs['budget'] = budgets

        min_budget = min(budgets)
        max_budget = max(budgets)
        normalized_sizes = [1 + 59 * (budget - min_budget) / (max_budget - min_budget) for budget in budgets]
        scaled_sizes = [((int(size) // 10) * 10) for size in normalized_sizes]
        g.vs['size'] = scaled_sizes

        all_movies_data.extend(country_grafoData)

        # Salvar o grafo original
        original_file_path = os.path.join(script_directory, f"grafo_filmes_{country}.graphml")
        g.write_graphml(original_file_path)

        # Executar o algoritmo de Prim para encontrar a árvore geradora mínima (MST)
        mst = g.spanning_tree(weights=None, return_tree=True)
        assign_weights_and_labels(mst)

        all_mst_edges.extend(mst.es)

        # Salvar o grafo MST
        mst_file_path = os.path.join(script_directory, f"grafo_filmes_mst_{country}.graphml")
        mst.write_graphml(mst_file_path)

# Criar e salvar o grafo com todos os filmes
if all_movies_data:
    all_vertices = len(all_movies_data)
    all_edges = []

    # Adicionar arestas para o grafo combinado
    for i in range(all_vertices):
        for j in range(i + 1, all_vertices):
            common_countries = set(all_movies_data[i]['production_countries']).intersection(set(all_movies_data[j]['production_countries']))
            if common_countries:
                all_edges.append((i, j))

    if all_edges:
        g_all = ig.Graph(all_vertices, all_edges)
        g_all.vs['label'] = [movie['title'] for movie in all_movies_data]

        budgets = [movie['budget'] if movie['budget'] > 0 else 1 for movie in all_movies_data]
        g_all.vs['budget'] = budgets

        min_budget = min(budgets)
        max_budget = max(budgets)
        normalized_sizes = [1 + 59 * (budget - min_budget) / (max_budget - min_budget) for budget in budgets]
        scaled_sizes = [((int(size) // 10) * 10) for size in normalized_sizes]
        g_all.vs['size'] = scaled_sizes

        # Salvar o grafo com todos os filmes
        all_file_path = os.path.join(script_directory, "grafo_filmes_todos_paises.graphml")
        g_all.write_graphml(all_file_path)

# Criar e salvar o grafo MST com todos os MSTs
if all_mst_edges:
    all_mst_g = ig.Graph(len(all_movies_data))
    all_mst_g.add_edges([e.tuple for e in all_mst_edges])
    
    # Definir os atributos 'budget' e 'label' no grafo MST combinado
    all_mst_g.vs['budget'] = [movie['budget'] for movie in all_movies_data]
    all_mst_g.vs['label'] = [movie['title'] for movie in all_movies_data]

    assign_weights_and_labels(all_mst_g)

    # Salvar o grafo MST com todos os MSTs
    all_mst_file_path = os.path.join(script_directory, "grafo_filmes_mst_todos_paises.graphml")
    all_mst_g.write_graphml(all_mst_file_path)

print('Processamento concluído.')
