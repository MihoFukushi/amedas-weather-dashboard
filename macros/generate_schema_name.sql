{#-
  デフォルトの dbt は target schema + "_" + custom schema (例: main_marts) を作る。
  個人プロジェクトでは custom schema 名をそのまま使う方が分かりやすいので上書きする。
-#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
