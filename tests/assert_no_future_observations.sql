-- singular test の例: 未来時刻の観測値が混入していたら失敗する(行が返る = 失敗)
select observed_at
from {{ ref('stg_amedas__observations') }}
where observed_at > current_timestamp + interval 1 day
