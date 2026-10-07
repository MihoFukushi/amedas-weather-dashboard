{#-
  品質フラグ(qc)が 0=正常 / 1=準正常 のものだけ値を採用し、それ以外は null にする。
  元の値とフラグは分析用に残す。
-#}

{% set elements = [
    ('temp', 'temperature_c'),
    ('humidity', 'humidity_pct'),
    ('precipitation1h', 'precipitation_1h_mm'),
    ('precipitation24h', 'precipitation_24h_mm'),
    ('wind', 'wind_speed_ms'),
    ('wind_direction', 'wind_direction_code'),
    ('pressure', 'pressure_hpa'),
    ('sun1h', 'sunshine_1h_h'),
    ('snow', 'snow_depth_cm'),
] %}

with source as (

    select * from {{ source('amedas', 'observations') }}

),

renamed as (

    select
        cast(station_id as varchar)     as station_id,
        cast(observed_at as timestamp)  as observed_at,
        cast(observed_at as date)       as observation_date,
        extract(hour from cast(observed_at as timestamp)) as observation_hour,
        {%- for src, dst in elements %}
        case when {{ src }}_qc in (0, 1) then cast({{ src }} as double) end as {{ dst }},
        cast({{ src }}_qc as integer) as {{ dst }}_qc{{ "," if not loop.last }}
        {%- endfor %}
    from source

)

select * from renamed
-- 同じ時刻のファイルが二重に存在しても 1 行に揃える
qualify row_number() over (partition by station_id, observed_at order by observed_at) = 1
