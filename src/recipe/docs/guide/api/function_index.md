# Function Index

[API 전체 목차](README.md) · [Class Index](class_index.md)

클래스에 소속되지 않은 최상위 함수를 알파벳순으로 나열한다. 클래스 메서드는 각 모듈의 Method Summary에서 찾는다.

| 함수 | 반환형 | 정의 모듈 |
| --- | --- | --- |
| [recipe_ingredient_parser._choose_amount](setup/recipe_ingredient_parser.md#function-_choose_amount) | `tuple[Decimal \| None, str \| None, list[str], int]` | `recipe_recommender/setup/recipe_ingredient_parser.py` |
| [recipe_register_service._clean_text](setup/recipe_register_service.md#function-_clean_text) | `str \| None` | `recipe_recommender/setup/recipe_register_service.py` |
| [database._close_manager](recipe_recommender/database.md#function-_close_manager) | `None` | `recipe_recommender/database.py` |
| [database_manager._configure_connection](common/database_manager.md#function-_configure_connection) | `None` | `common/database_manager.py` |
| [neo4j_db_session._cypher_literal](common/neo4j_db_session.md#function-_cypher_literal) | `str` | `common/neo4j_db_session.py` |
| [neo4j_db_session._cypher_name](common/neo4j_db_session.md#function-_cypher_name) | `str` | `common/neo4j_db_session.py` |
| [neo4j_db_session._cypher_parameter_tokens](common/neo4j_db_session.md#function-_cypher_parameter_tokens) | `list[tuple[int, int, str]]` | `common/neo4j_db_session.py` |
| [neo4j_db_session._cypher_string](common/neo4j_db_session.md#function-_cypher_string) | `str` | `common/neo4j_db_session.py` |
| [neo4j_db_session._driver_types](common/neo4j_db_session.md#function-_driver_types) | `SimpleNamespace` | `common/neo4j_db_session.py` |
| [neo4j_db_session._format_counters](common/neo4j_db_session.md#function-_format_counters) | `str` | `common/neo4j_db_session.py` |
| [neo4j_db_session._format_result_cell](common/neo4j_db_session.md#function-_format_result_cell) | `str` | `common/neo4j_db_session.py` |
| [database._get_manager](recipe_recommender/database.md#function-_get_manager) | `타입 힌트 없음` | `recipe_recommender/database.py` |
| [neo4j_db_session._inline_literal](common/neo4j_db_session.md#function-_inline_literal) | `str` | `common/neo4j_db_session.py` |
| [recipe_graph_load_service._key](setup/recipe_graph_load_service.md#function-_key) | `tuple` | `recipe_recommender/setup/recipe_graph_load_service.py` |
| [recipe_rebuild._lock_source](tools/recipe_rebuild.md#function-_lock_source) | `None` | `recipe_recommender/tools/recipe_rebuild.py` |
| [database._mapper_root_for](recipe_recommender/database.md#function-_mapper_root_for) | `Path` | `recipe_recommender/database.py` |
| [query_logger._normalize_key](common/query_logger.md#function-_normalize_key) | `str` | `common/query_logger.py` |
| [recipe_register_service._null_if_empty](setup/recipe_register_service.md#function-_null_if_empty) | `str \| None` | `recipe_recommender/setup/recipe_register_service.py` |
| [register_recipe_csv._print_list](setup/register_recipe_csv.md#function-_print_list) | `None` | `recipe_recommender/setup/register_recipe_csv.py` |
| [search_recipe._print_rows](recipe_recommender/search_recipe.md#function-_print_rows) | `None` | `recipe_recommender/search_recipe.py` |
| [check_supabase_connection._run_query](tools/check_supabase_connection.md#function-_run_query) | `타입 힌트 없음` | `recipe_recommender/tools/check_supabase_connection.py` |
| [neo4j_db_session._server_ms](common/neo4j_db_session.md#function-_server_ms) | `int \| None` | `common/neo4j_db_session.py` |
| [recipe_rebuild._sha256](tools/recipe_rebuild.md#function-_sha256) | `str` | `recipe_recommender/tools/recipe_rebuild.py` |
| [recipe_ingredient_parser._split_header](setup/recipe_ingredient_parser.md#function-_split_header) | `tuple[str \| None, str \| None, str]` | `recipe_recommender/setup/recipe_ingredient_parser.py` |
| [recipe_ingredient_parser._split_inline_sections](setup/recipe_ingredient_parser.md#function-_split_inline_sections) | `list[tuple[str \| None, str \| None]]` | `recipe_recommender/setup/recipe_ingredient_parser.py` |
| [recipe_ingredient_parser._split_item_headers](setup/recipe_ingredient_parser.md#function-_split_item_headers) | `list[tuple[str \| None, str \| None]]` | `recipe_recommender/setup/recipe_ingredient_parser.py` |
| [recipe_ingredient_parser._status_for_name](setup/recipe_ingredient_parser.md#function-_status_for_name) | `str` | `recipe_recommender/setup/recipe_ingredient_parser.py` |
| [recipe_graph_load_service._step_rows](setup/recipe_graph_load_service.md#function-_step_rows) | `list[dict]` | `recipe_recommender/setup/recipe_graph_load_service.py` |
| [check_supabase_connection._target_label](tools/check_supabase_connection.md#function-_target_label) | `str` | `recipe_recommender/tools/check_supabase_connection.py` |
| [recipe_graph_load_service._unique_keys](setup/recipe_graph_load_service.md#function-_unique_keys) | `set[tuple]` | `recipe_recommender/setup/recipe_graph_load_service.py` |
| [recipe_rebuild.backup](tools/recipe_rebuild.md#function-backup) | `dict` | `recipe_recommender/tools/recipe_rebuild.py` |
| [recipe_rebuild.build](tools/recipe_rebuild.md#function-build) | `None` | `recipe_recommender/tools/recipe_rebuild.py` |
| [pantry_graphrag.build_context](recipe_recommender/pantry_graphrag.md#function-build_context) | `list[dict]` | `recipe_recommender/pantry_graphrag.py` |
| [recipe_rebuild.build_target](tools/recipe_rebuild.md#function-build_target) | `list[dict]` | `recipe_recommender/tools/recipe_rebuild.py` |
| [database_manager.camel_dict_row](common/database_manager.md#function-camel_dict_row) | `RowMaker[dict[str, Any]]` | `common/database_manager.py` |
| [recipe_rebuild.catalog_columns](tools/recipe_rebuild.md#function-catalog_columns) | `dict[tuple[str, str], tuple[str, bool]]` | `recipe_recommender/tools/recipe_rebuild.py` |
| [recipe_rebuild.catalog_objects](tools/recipe_rebuild.md#function-catalog_objects) | `list[dict]` | `recipe_recommender/tools/recipe_rebuild.py` |
| [recipe_rebuild.catalog_pks](tools/recipe_rebuild.md#function-catalog_pks) | `dict[str, list[str]]` | `recipe_recommender/tools/recipe_rebuild.py` |
| [recipe_rebuild.catalog_tables](tools/recipe_rebuild.md#function-catalog_tables) | `list[str]` | `recipe_recommender/tools/recipe_rebuild.py` |
| [recipe_rebuild.check_legacy_source](tools/recipe_rebuild.md#function-check_legacy_source) | `None` | `recipe_recommender/tools/recipe_rebuild.py` |
| [recipe_rebuild.check_target_structure](tools/recipe_rebuild.md#function-check_target_structure) | `list[str]` | `recipe_recommender/tools/recipe_rebuild.py` |
| [database.classify_pool_mode](recipe_recommender/database.md#function-classify_pool_mode) | `str` | `recipe_recommender/database.py` |
| [config.configure_query_logging](recipe_recommender/config.md#function-configure_query_logging) | `bool` | `recipe_recommender/config.py` |
| [sql_schema.configured_schema](recipe_recommender/sql_schema.md#function-configured_schema) | `str` | `recipe_recommender/sql_schema.py` |
| [recipe_rebuild.connect](tools/recipe_rebuild.md#function-connect) | `타입 힌트 없음` | `recipe_recommender/tools/recipe_rebuild.py` |
| [pantry_graphrag.create_llm](recipe_recommender/pantry_graphrag.md#function-create_llm) | `타입 힌트 없음` | `recipe_recommender/pantry_graphrag.py` |
| [neo4j_connection.create_neo4j_driver](recipe_recommender/neo4j_connection.md#function-create_neo4j_driver) | `타입 힌트 없음` | `recipe_recommender/neo4j_connection.py` |
| [database.create_recipe_sql_session](recipe_recommender/database.md#function-create_recipe_sql_session) | `타입 힌트 없음` | `recipe_recommender/database.py` |
| [recipe_rebuild.cutover](tools/recipe_rebuild.md#function-cutover) | `None` | `recipe_recommender/tools/recipe_rebuild.py` |
| [recipe_rebuild.describe_target](tools/recipe_rebuild.md#function-describe_target) | `dict` | `recipe_recommender/tools/recipe_rebuild.py` |
| [pantry_recommend_service.display_image_url](recipe_recommender/pantry_recommend_service.md#function-display_image_url) | `str \| None` | `recipe_recommender/pantry_recommend_service.py` |
| [neo4j_connection.driver_arguments](recipe_recommender/neo4j_connection.md#function-driver_arguments) | `tuple[str, dict]` | `recipe_recommender/neo4j_connection.py` |
| [recipe_rebuild.drop_schema](tools/recipe_rebuild.md#function-drop_schema) | `None` | `recipe_recommender/tools/recipe_rebuild.py` |
| [streamlit_app.escape_markdown](streamlit_app.md#function-escape_markdown) | `str` | `streamlit_app.py` |
| [recipe_register_service.evaluate_nutrition](setup/recipe_register_service.md#function-evaluate_nutrition) | `tuple[dict[str, Decimal \| None], str, str \| None]` | `recipe_recommender/setup/recipe_register_service.py` |
| [pantry_graphrag.foreign_ingredients](recipe_recommender/pantry_graphrag.md#function-foreign_ingredients) | `list[str]` | `recipe_recommender/pantry_graphrag.py` |
| [neo4j_db_session.format_graph_value](common/neo4j_db_session.md#function-format_graph_value) | `str` | `common/neo4j_db_session.py` |
| [streamlit_app.get_graph_question_service](streamlit_app.md#function-get_graph_question_service) | `GraphQuestionService` | `streamlit_app.py` |
| [streamlit_app.get_log_check_search_service](streamlit_app.md#function-get_log_check_search_service) | `타입 힌트 없음` | `streamlit_app.py` |
| [streamlit_app.get_pipeline](streamlit_app.md#function-get_pipeline) | `타입 힌트 없음` | `streamlit_app.py` |
| [database.get_pool_mode](recipe_recommender/database.md#function-get_pool_mode) | `str` | `recipe_recommender/database.py` |
| [streamlit_app.graph_inputs](streamlit_app.md#function-graph_inputs) | `dict` | `streamlit_app.py` |
| [streamlit_app.graph_summary](streamlit_app.md#function-graph_summary) | `str \| None` | `streamlit_app.py` |
| [streamlit_app.graph_table](streamlit_app.md#function-graph_table) | `list[dict]` | `streamlit_app.py` |
| [pantry_graphrag.grounded_reason](recipe_recommender/pantry_graphrag.md#function-grounded_reason) | `str` | `recipe_recommender/pantry_graphrag.py` |
| [pantry_graphrag.grounded_summary](recipe_recommender/pantry_graphrag.md#function-grounded_summary) | `str` | `recipe_recommender/pantry_graphrag.py` |
| [pantry_graphrag.has_final_consonant](recipe_recommender/pantry_graphrag.md#function-has_final_consonant) | `bool \| None` | `recipe_recommender/pantry_graphrag.py` |
| [_connection_util.initialize](tools/_connection_util.md#function-initialize) | `None` | `recipe_recommender/tools/_connection_util.py` |
| [recipe_rebuild.inspect](tools/recipe_rebuild.md#function-inspect) | `None` | `recipe_recommender/tools/recipe_rebuild.py` |
| [config.is_local_dev](recipe_recommender/config.md#function-is_local_dev) | `bool` | `recipe_recommender/config.py` |
| [query_logger.is_numeric_sequence](common/query_logger.md#function-is_numeric_sequence) | `bool` | `common/query_logger.py` |
| [pantry_graphrag.josa](recipe_recommender/pantry_graphrag.md#function-josa) | `str` | `recipe_recommender/pantry_graphrag.py` |
| [pantry_graphrag.josa_ro](recipe_recommender/pantry_graphrag.md#function-josa_ro) | `str` | `recipe_recommender/pantry_graphrag.py` |
| [pantry_graphrag.list_text](recipe_recommender/pantry_graphrag.md#function-list_text) | `str` | `recipe_recommender/pantry_graphrag.py` |
| [recipe_register_service.load_cook_method_seed](setup/recipe_register_service.md#function-load_cook_method_seed) | `dict[str, str]` | `recipe_recommender/setup/recipe_register_service.py` |
| [recipe_register_service.load_ingredient_seed](setup/recipe_register_service.md#function-load_ingredient_seed) | `IngredientSeed` | `recipe_recommender/setup/recipe_register_service.py` |
| [recipe_rebuild.load_manifest](tools/recipe_rebuild.md#function-load_manifest) | `dict` | `recipe_recommender/tools/recipe_rebuild.py` |
| [config.load_project_environment](recipe_recommender/config.md#function-load_project_environment) | `None` | `recipe_recommender/config.py` |
| [config.local_dev_query_log_default](recipe_recommender/config.md#function-local_dev_query_log_default) | `bool` | `recipe_recommender/config.py` |
| [main.main](recipe_recommender/main.md#function-main) | `int` | `recipe_recommender/main.py` |
| [search_recipe.main](recipe_recommender/search_recipe.md#function-main) | `int` | `recipe_recommender/search_recipe.py` |
| [load_recipe_graph.main](setup/load_recipe_graph.md#function-main) | `int` | `recipe_recommender/setup/load_recipe_graph.py` |
| [register_recipe_csv.main](setup/register_recipe_csv.md#function-main) | `int` | `recipe_recommender/setup/register_recipe_csv.py` |
| [check_neo4j_connection.main](tools/check_neo4j_connection.md#function-main) | `int` | `recipe_recommender/tools/check_neo4j_connection.py` |
| [check_supabase_connection.main](tools/check_supabase_connection.md#function-main) | `int` | `recipe_recommender/tools/check_supabase_connection.py` |
| [rebuild_recipe_schema.main](tools/rebuild_recipe_schema.md#function-main) | `int` | `recipe_recommender/tools/rebuild_recipe_schema.py` |
| [recipe_rebuild.main](tools/recipe_rebuild.md#function-main) | `int` | `recipe_recommender/tools/recipe_rebuild.py` |
| [reset_recipe_data.main](tools/reset_recipe_data.md#function-main) | `int` | `recipe_recommender/tools/reset_recipe_data.py` |
| [pantry_graphrag.mask_phrases](recipe_recommender/pantry_graphrag.md#function-mask_phrases) | `str` | `recipe_recommender/pantry_graphrag.py` |
| [name_normalization.normalize_name](recipe_recommender/name_normalization.md#function-normalize_name) | `str` | `recipe_recommender/name_normalization.py` |
| [recipe_register_service.normalize_newlines](setup/recipe_register_service.md#function-normalize_newlines) | `str \| None` | `recipe_recommender/setup/recipe_register_service.py` |
| [search_recipe.parse_args](recipe_recommender/search_recipe.md#function-parse_args) | `argparse.Namespace` | `recipe_recommender/search_recipe.py` |
| [register_recipe_csv.parse_args](setup/register_recipe_csv.md#function-parse_args) | `argparse.Namespace` | `recipe_recommender/setup/register_recipe_csv.py` |
| [recipe_rebuild.parse_args](tools/recipe_rebuild.md#function-parse_args) | `argparse.Namespace` | `recipe_recommender/tools/recipe_rebuild.py` |
| [recipe_ingredient_parser.parse_ingredient_text](setup/recipe_ingredient_parser.md#function-parse_ingredient_text) | `list[ParsedIngredient]` | `recipe_recommender/setup/recipe_ingredient_parser.py` |
| [recipe_ingredient_parser.parse_item](setup/recipe_ingredient_parser.md#function-parse_item) | `tuple[str \| None, Decimal \| None, str \| None, str, list[str]]` | `recipe_recommender/setup/recipe_ingredient_parser.py` |
| [recipe_ingredient_parser.parse_quantity](setup/recipe_ingredient_parser.md#function-parse_quantity) | `Decimal \| None` | `recipe_recommender/setup/recipe_ingredient_parser.py` |
| [config.prepare_common_imports](recipe_recommender/config.md#function-prepare_common_imports) | `None` | `recipe_recommender/config.py` |
| [config.prepare_imports](recipe_recommender/config.md#function-prepare_imports) | `None` | `recipe_recommender/config.py` |
| [search_recipe.print_detail](recipe_recommender/search_recipe.md#function-print_detail) | `None` | `recipe_recommender/search_recipe.py` |
| [search_recipe.print_page](recipe_recommender/search_recipe.md#function-print_page) | `None` | `recipe_recommender/search_recipe.py` |
| [register_recipe_csv.print_report](setup/register_recipe_csv.md#function-print_report) | `None` | `recipe_recommender/setup/register_recipe_csv.py` |
| [_sql_script.print_state](tools/_sql_script.md#function-print_state) | `None` | `recipe_recommender/tools/_sql_script.py` |
| [recipe_rebuild.print_validation](tools/recipe_rebuild.md#function-print_validation) | `bool` | `recipe_recommender/tools/recipe_rebuild.py` |
| [config.project_root](recipe_recommender/config.md#function-project_root) | `Path` | `recipe_recommender/config.py` |
| [config.query_log_enabled](recipe_recommender/config.md#function-query_log_enabled) | `bool` | `recipe_recommender/config.py` |
| [config.query_logging_active](recipe_recommender/config.md#function-query_logging_active) | `bool` | `recipe_recommender/config.py` |
| [recipe_register_service.raw_seq_for](setup/recipe_register_service.md#function-raw_seq_for) | `str` | `recipe_recommender/setup/recipe_register_service.py` |
| [recipe_rebuild.read_only](tools/recipe_rebuild.md#function-read_only) | `타입 힌트 없음` | `recipe_recommender/tools/recipe_rebuild.py` |
| [database.recipe_connection](recipe_recommender/database.md#function-recipe_connection) | `Iterator[object]` | `recipe_recommender/database.py` |
| [recipe_graph_source_repository.recipe_graph_row](setup/recipe_graph_source_repository.md#function-recipe_graph_row) | `dict` | `recipe_recommender/setup/recipe_graph_source_repository.py` |
| [neo4j_db_session.render_cypher_inline](common/neo4j_db_session.md#function-render_cypher_inline) | `tuple[str \| None, str]` | `common/neo4j_db_session.py` |
| [neo4j_db_session.render_cypher_log](common/neo4j_db_session.md#function-render_cypher_log) | `str` | `common/neo4j_db_session.py` |
| [neo4j_db_session.render_cypher_params](common/neo4j_db_session.md#function-render_cypher_params) | `str` | `common/neo4j_db_session.py` |
| [sql_schema.render_schema_sql](recipe_recommender/sql_schema.md#function-render_schema_sql) | `str` | `recipe_recommender/sql_schema.py` |
| [recipe_rebuild.require_confirmed_db](tools/recipe_rebuild.md#function-require_confirmed_db) | `dict` | `recipe_recommender/tools/recipe_rebuild.py` |
| [recipe_register_service.resolve_cook_method_map](setup/recipe_register_service.md#function-resolve_cook_method_map) | `dict[str, str]` | `recipe_recommender/setup/recipe_register_service.py` |
| [recipe_rebuild.restore_test](tools/recipe_rebuild.md#function-restore_test) | `list[str]` | `recipe_recommender/tools/recipe_rebuild.py` |
| [recipe_rebuild.rollback_cutover](tools/recipe_rebuild.md#function-rollback_cutover) | `str` | `recipe_recommender/tools/recipe_rebuild.py` |
| [streamlit_app.run_graph_question](streamlit_app.md#function-run_graph_question) | `GraphAnswer` | `streamlit_app.py` |
| [streamlit_app.run_pipeline](streamlit_app.md#function-run_pipeline) | `dict` | `streamlit_app.py` |
| [streamlit_app.run_postgres_log_check](streamlit_app.md#function-run_postgres_log_check) | `None` | `streamlit_app.py` |
| [_sql_script.run_sql_script](tools/_sql_script.md#function-run_sql_script) | `int` | `recipe_recommender/tools/_sql_script.py` |
| [recipe_rebuild.run_validation](tools/recipe_rebuild.md#function-run_validation) | `list[dict]` | `recipe_recommender/tools/recipe_rebuild.py` |
| [_connection_util.safe_error](tools/_connection_util.md#function-safe_error) | `str` | `recipe_recommender/tools/_connection_util.py` |
| [pantry_graphrag.scan_vocabulary_terms](recipe_recommender/pantry_graphrag.md#function-scan_vocabulary_terms) | `list[str]` | `recipe_recommender/pantry_graphrag.py` |
| [recipe_rebuild.schema_comment](tools/recipe_rebuild.md#function-schema_comment) | `str \| None` | `recipe_recommender/tools/recipe_rebuild.py` |
| [recipe_rebuild.schema_exists](tools/recipe_rebuild.md#function-schema_exists) | `bool` | `recipe_recommender/tools/recipe_rebuild.py` |
| [streamlit_app.show_graph_answer](streamlit_app.md#function-show_graph_answer) | `None` | `streamlit_app.py` |
| [streamlit_app.show_graph_explorer](streamlit_app.md#function-show_graph_explorer) | `None` | `streamlit_app.py` |
| [streamlit_app.show_image](streamlit_app.md#function-show_image) | `bool` | `streamlit_app.py` |
| [streamlit_app.show_llm_status](streamlit_app.md#function-show_llm_status) | `None` | `streamlit_app.py` |
| [streamlit_app.show_steps](streamlit_app.md#function-show_steps) | `None` | `streamlit_app.py` |
| [database_manager.snake_to_camel](common/database_manager.md#function-snake_to_camel) | `str` | `common/database_manager.py` |
| [streamlit_app.source_badge](streamlit_app.md#function-source_badge) | `None` | `streamlit_app.py` |
| [recipe_ingredient_parser.split_items](setup/recipe_ingredient_parser.md#function-split_items) | `list[str]` | `recipe_recommender/setup/recipe_ingredient_parser.py` |
| [pantry_recommend_service.split_terms](recipe_recommender/pantry_recommend_service.md#function-split_terms) | `list[str]` | `recipe_recommender/pantry_recommend_service.py` |
| [recipe_register_service.strip_step_prefix](setup/recipe_register_service.md#function-strip_step_prefix) | `str` | `recipe_recommender/setup/recipe_register_service.py` |
| [neo4j_db_session.summary_counters](common/neo4j_db_session.md#function-summary_counters) | `dict[str, int]` | `common/neo4j_db_session.py` |
| [recipe_rebuild.table_fingerprints](tools/recipe_rebuild.md#function-table_fingerprints) | `dict[str, dict]` | `recipe_recommender/tools/recipe_rebuild.py` |
| [recipe_rebuild.target_label](tools/recipe_rebuild.md#function-target_label) | `str` | `recipe_recommender/tools/recipe_rebuild.py` |
| [pantry_graphrag.terms_in_question](recipe_recommender/pantry_graphrag.md#function-terms_in_question) | `list[str]` | `recipe_recommender/pantry_graphrag.py` |
| [neo4j_connection.trusted_ca_file](recipe_recommender/neo4j_connection.md#function-trusted_ca_file) | `str` | `recipe_recommender/neo4j_connection.py` |
| [recipe_rebuild.validate](tools/recipe_rebuild.md#function-validate) | `bool` | `recipe_recommender/tools/recipe_rebuild.py` |
| [pantry_graphrag.validate_answer](recipe_recommender/pantry_graphrag.md#function-validate_answer) | `tuple[dict, list[str]]` | `recipe_recommender/pantry_graphrag.py` |
| [sql_schema.validate_schema_name](recipe_recommender/sql_schema.md#function-validate_schema_name) | `str` | `recipe_recommender/sql_schema.py` |
| [recipe_rebuild.verify_backup_files](tools/recipe_rebuild.md#function-verify_backup_files) | `list[str]` | `recipe_recommender/tools/recipe_rebuild.py` |
| [recipe_rebuild.verify_backup_live](tools/recipe_rebuild.md#function-verify_backup_live) | `list[str]` | `recipe_recommender/tools/recipe_rebuild.py` |
