{#-
  直近の観測日について「最高気温」「最低気温」「降水量」「最大風速」の全国ランキング上位10地点。
  Jinja の for ループで同じ形の SQL を4本生成して union する(dbt らしい書き方の例)。
-#}

{% set rankings = [
    {'type': 'hottest',  'metric': 'temp_max_c',       'direction': 'desc'},
    {'type': 'coldest',  'metric': 'temp_min_c',       'direction': 'asc'},
    {'type': 'wettest',  'metric': 'precipitation_mm', 'direction': 'desc'},
    {'type': 'windiest', 'metric': 'wind_max_ms',      'direction': 'desc'},
] %}

with daily as (

    select * from {{ ref('daily_station_weather') }}
    where observation_date = (select max(observation_date) from {{ ref('daily_station_weather') }})

)

{% for r in rankings %}
select
    '{{ r.type }}'          as ranking_type,
    '{{ r.metric }}'        as metric_name,
    observation_date,
    station_id,
    station_name,
    pref_name,
    {{ r.metric }}          as metric_value,
    rank() over (order by {{ r.metric }} {{ r.direction }}) as ranking
from daily
where {{ r.metric }} is not null
qualify ranking <= 10
{% if not loop.last %}
union all
{% endif %}
{% endfor %}
