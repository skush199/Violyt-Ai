-- Sample database seed for local development
-- Assumes:
-- 1. PostgreSQL schema has already been created via Alembic
-- 2. The API has been started once so RBAC seed data exists
-- 3. The role code `tenant_admin` is present in `roles`

BEGIN;

INSERT INTO users (
    id,
    tenant_id,
    email,
    full_name,
    phone_number,
    hashed_password,
    is_active,
    is_activated,
    last_login_at,
    metadata_json
) VALUES (
    '00000000-0000-0000-0000-000000000001',
    NULL,
    'owner@violyt.ai',
    'Sample Platform Owner',
    '+91-9000000009',
    NULL,
    TRUE,
    FALSE,
    NULL,
    '{}'::jsonb
) ON CONFLICT (id) DO NOTHING;

INSERT INTO activation_tokens (
    id,
    user_id,
    token,
    expires_at,
    used_at
) VALUES (
    '00000000-0000-0000-0000-000000000002',
    '00000000-0000-0000-0000-000000000001',
    'sample-activation-token-owner',
    NOW() + INTERVAL '30 days',
    NULL
) ON CONFLICT (id) DO NOTHING;

INSERT INTO user_roles (
    id,
    user_id,
    role_id,
    brand_space_id
)
SELECT
    '00000000-0000-0000-0000-000000000003',
    '00000000-0000-0000-0000-000000000001',
    roles.id,
    NULL
FROM roles
WHERE roles.code = 'super_admin'
ON CONFLICT DO NOTHING;

INSERT INTO tenants (
    id,
    name,
    slug,
    contact_email,
    contact_number,
    address,
    logo_asset_path,
    is_active,
    metadata_json
) VALUES (
    '11111111-1111-1111-1111-111111111111',
    'Sample Tenant',
    'sample-tenant',
    'admin@sampletenant.com',
    '+91-9000000000',
    'Bengaluru, India',
    NULL,
    TRUE,
    '{}'::jsonb
) ON CONFLICT (id) DO NOTHING;

INSERT INTO usage_limits (
    id,
    tenant_id,
    max_users,
    max_brand_spaces,
    max_content_generations,
    max_image_generations,
    max_ocr_pages
) VALUES (
    '22222222-2222-2222-2222-222222222222',
    '11111111-1111-1111-1111-111111111111',
    25,
    10,
    5000,
    1000,
    2000
) ON CONFLICT (id) DO NOTHING;

INSERT INTO users (
    id,
    tenant_id,
    email,
    full_name,
    phone_number,
    hashed_password,
    is_active,
    is_activated,
    last_login_at,
    metadata_json
) VALUES (
    '33333333-3333-3333-3333-333333333333',
    '11111111-1111-1111-1111-111111111111',
    'admin@sampletenant.com',
    'Sample Tenant Admin',
    '+91-9000000001',
    NULL,
    TRUE,
    FALSE,
    NULL,
    '{}'::jsonb
) ON CONFLICT (id) DO NOTHING;

INSERT INTO activation_tokens (
    id,
    user_id,
    token,
    expires_at,
    used_at
) VALUES (
    '44444444-4444-4444-4444-444444444444',
    '33333333-3333-3333-3333-333333333333',
    'sample-activation-token-admin',
    NOW() + INTERVAL '30 days',
    NULL
) ON CONFLICT (id) DO NOTHING;

INSERT INTO user_roles (
    id,
    user_id,
    role_id,
    brand_space_id
)
SELECT
    '55555555-5555-5555-5555-555555555555',
    '33333333-3333-3333-3333-333333333333',
    roles.id,
    NULL
FROM roles
WHERE roles.code = 'tenant_admin'
ON CONFLICT DO NOTHING;

INSERT INTO brand_spaces (
    id,
    tenant_id,
    name,
    slug,
    description,
    industry_category,
    sub_industry,
    geography_country,
    geography_city,
    audience_type,
    lifecycle_state,
    is_finalized,
    overview_snapshot,
    resolved_brand_context,
    default_persona_id,
    deleted_at
) VALUES (
    '66666666-6666-6666-6666-666666666666',
    '11111111-1111-1111-1111-111111111111',
    'Sample Brand',
    'sample-brand',
    'A sample active brand space used for local development and API testing.',
    'Retail',
    'Beauty',
    'India',
    'Bengaluru',
    'B2C',
    'active',
    TRUE,
    '{"status":"ready_for_generation","wizard_progress":"complete"}'::jsonb,
    '{"brand_name":"Sample Brand","identity":{"brand_name":"Sample Brand","brand_description":"Science-backed beauty products","social_profiles":{"linkedin":"https://linkedin.com/company/sample-brand","instagram":"https://instagram.com/samplebrand","x":"https://x.com/samplebrand"}},"foundations":{"brand_mission":"Make evidence-led skincare simple and trustworthy.","brand_promise":"Gentle, credible daily care.","market_positioning":"Premium science-backed beauty."},"voice_tone":{"tone_attributes":["confident","clear","warm"],"primary_emotion":"trust"},"visual_identity":{"brand_mood":"modern","visual_style":"clean editorial","brand_color_palette":{"primary":"#111111","secondary":"#F6E7D8"}},"prompt_intelligence":{"platform_rules":{"linkedin":{"style":"thought_leadership"},"instagram":{"style":"visual storytelling"},"x":{"style":"short-form sharp"},"youtube_thumbnail":{"style":"thumbnail headline"}}},"guardrails":{"blocked_words":["cheap"],"restricted_claims":["guaranteed results"]},"context_priority":{"highest":["guardrails","identity","foundations","voice_tone","visual_identity","prompt_intelligence"],"supplemental":["strategy","brand","campaign_history","template","metadata"]}}'::jsonb,
    NULL,
    NULL
) ON CONFLICT (id) DO NOTHING;

INSERT INTO brand_space_members (
    id,
    tenant_id,
    brand_space_id,
    user_id,
    can_manage
) VALUES (
    '77777777-7777-7777-7777-777777777777',
    '11111111-1111-1111-1111-111111111111',
    '66666666-6666-6666-6666-666666666666',
    '33333333-3333-3333-3333-333333333333',
    TRUE
) ON CONFLICT DO NOTHING;

INSERT INTO brand_configuration_sections (
    id,
    tenant_id,
    brand_space_id,
    section_code,
    version,
    is_current,
    completion_percent,
    payload
) VALUES
(
    '88888888-8888-8888-8888-888888888881',
    '11111111-1111-1111-1111-111111111111',
    '66666666-6666-6666-6666-666666666666',
    'identity',
    1,
    TRUE,
    100,
    '{"brand_name":"Sample Brand","brand_description":"Science-backed beauty products","industry_category":"Retail","sub_industry":"Beauty"}'::jsonb
),
(
    '88888888-8888-8888-8888-888888888882',
    '11111111-1111-1111-1111-111111111111',
    '66666666-6666-6666-6666-666666666666',
    'foundations',
    1,
    TRUE,
    100,
    '{"brand_mission":"Make evidence-led skincare simple and trustworthy.","brand_promise":"Gentle, credible daily care.","market_positioning":"Premium science-backed beauty."}'::jsonb
),
(
    '88888888-8888-8888-8888-888888888883',
    '11111111-1111-1111-1111-111111111111',
    '66666666-6666-6666-6666-666666666666',
    'voice_tone',
    1,
    TRUE,
    100,
    '{"tone_attributes":["confident","clear","warm"],"primary_emotion":"trust","content_complexity":"simple"}'::jsonb
),
(
    '88888888-8888-8888-8888-888888888884',
    '11111111-1111-1111-1111-111111111111',
    '66666666-6666-6666-6666-666666666666',
    'visual_identity',
    1,
    TRUE,
    100,
    '{"brand_mood":"modern","visual_style":"clean editorial","brand_color_palette":{"primary":"#111111","secondary":"#F6E7D8"}}'::jsonb
),
(
    '88888888-8888-8888-8888-888888888885',
    '11111111-1111-1111-1111-111111111111',
    '66666666-6666-6666-6666-666666666666',
    'prompt_intelligence',
    1,
    TRUE,
    100,
    '{"platform_rules":{"linkedin":{"style":"thought leadership"},"instagram":{"style":"visual storytelling"},"x":{"style":"concise"},"youtube_thumbnail":{"style":"high impact"}},"prompt_starters":[{"label":"Launch post","prompt":"Create a launch-ready post"}]}'::jsonb
)
ON CONFLICT DO NOTHING;

INSERT INTO personas (
    id,
    tenant_id,
    brand_space_id,
    name,
    role,
    psychographics,
    demographics,
    audience_goals,
    motivations,
    fears_and_pain_points,
    objections,
    content_behavior,
    language_preference,
    is_default
) VALUES (
    '99999999-9999-9999-9999-999999999999',
    '11111111-1111-1111-1111-111111111111',
    '66666666-6666-6666-6666-666666666666',
    'Urban Skincare Buyer',
    'Primary buyer persona',
    '{"lifestyle":"busy professional","purchase_driver":"trust and proof"}'::jsonb,
    '{"age_range":"25-34","region":"India"}'::jsonb,
    '["find effective skincare","save time"]'::jsonb,
    '["confidence","reliability"]'::jsonb,
    '["skin sensitivity","wasting money"]'::jsonb,
    '["price concern","ingredient confusion"]'::jsonb,
    '{"preferred_platforms":["instagram","linkedin"]}'::jsonb,
    'English',
    TRUE
) ON CONFLICT (id) DO NOTHING;

UPDATE brand_spaces
SET default_persona_id = '99999999-9999-9999-9999-999999999999'
WHERE id = '66666666-6666-6666-6666-666666666666';

INSERT INTO guardrails (
    id,
    tenant_id,
    brand_space_id,
    positive_word_bank,
    replaceable_words,
    negative_word_bank,
    dos,
    donts,
    forbidden_prompt_patterns,
    restricted_topics,
    restricted_claims,
    blocked_words,
    custom_rules
) VALUES (
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    '11111111-1111-1111-1111-111111111111',
    '66666666-6666-6666-6666-666666666666',
    '["trusted","gentle","proven"]'::jsonb,
    '["cheap"]'::jsonb,
    '["aggressive"]'::jsonb,
    '["Use evidence-led language","Stay brand-safe"]'::jsonb,
    '["Do not overclaim","Do not sound clickbait"]'::jsonb,
    '["promise miracle cures"]'::jsonb,
    '["medical diagnosis"]'::jsonb,
    '["guaranteed results"]'::jsonb,
    '["cheap"]'::jsonb,
    '["Prefer calm, premium copy"]'::jsonb
) ON CONFLICT (id) DO NOTHING;

INSERT INTO objectives (
    id,
    tenant_id,
    brand_space_id,
    name,
    description,
    content_type,
    platform_scope,
    is_default,
    configuration
) VALUES (
    'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
    '11111111-1111-1111-1111-111111111111',
    '66666666-6666-6666-6666-666666666666',
    'Lead Generation',
    'Generate high-quality awareness and lead-focused content.',
    'social_post',
    'linkedin',
    TRUE,
    '{"cta_style":"learn_more","focus":"trust"}'::jsonb
) ON CONFLICT (id) DO NOTHING;

INSERT INTO sessions (
    id,
    tenant_id,
    brand_space_id,
    user_id,
    title,
    session_kind,
    studio_panel,
    conversational_context,
    is_active
) VALUES (
    'cccccccc-cccc-cccc-cccc-cccccccccccc',
    '11111111-1111-1111-1111-111111111111',
    '66666666-6666-6666-6666-666666666666',
    '33333333-3333-3333-3333-333333333333',
    'Sample Chat Session',
    'chat',
    '{"format":"static","platform_preset":"linkedin","file_type":"png","size":{"width":1200,"height":627}}'::jsonb,
    '{"message_count":2,"last_user_prompt":"Create a launch post for our serum"}'::jsonb,
    TRUE
) ON CONFLICT (id) DO NOTHING;

INSERT INTO content_history (
    id,
    tenant_id,
    brand_space_id,
    session_id,
    folder_id,
    parent_version_id,
    created_by,
    lifecycle_state,
    content_type,
    title,
    prompt,
    selected_persona_id,
    selected_template_id,
    objective_id,
    studio_panel,
    generated_payload,
    blueprint_payload,
    explainability_metadata,
    tone_score,
    tone_feedback,
    deleted_at
) VALUES (
    'dddddddd-dddd-dddd-dddd-dddddddddddd',
    '11111111-1111-1111-1111-111111111111',
    '66666666-6666-6666-6666-666666666666',
    'cccccccc-cccc-cccc-cccc-cccccccccccc',
    NULL,
    NULL,
    '33333333-3333-3333-3333-333333333333',
    'generated',
    'content',
    'Meet Your New Daily Serum',
    'Create a launch post for our serum',
    '99999999-9999-9999-9999-999999999999',
    NULL,
    'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
    '{"format":"static","platform_preset":"linkedin","file_type":"png","size":{"width":1200,"height":627}}'::jsonb,
    '{"headline":"Meet Your New Daily Serum","body":"A calm, science-backed formula designed for real routines and real results.","cta":"Learn more","hashtags":["#SampleBrand","#Skincare"]}'::jsonb,
    '{"layout_type":"single-panel","zones":[{"zone_id":"headline","role":"headline","x":72,"y":48,"width":680,"height":160,"max_lines":3},{"zone_id":"body","role":"body","x":72,"y":236,"width":680,"height":220,"max_lines":7},{"zone_id":"image","role":"image","x":800,"y":120,"width":328,"height":360},{"zone_id":"cta","role":"cta","x":72,"y":500,"width":300,"height":84,"max_lines":2}],"hierarchy":["headline","body","cta"],"text_blocks":[{"role":"headline","text":"Meet Your New Daily Serum"},{"role":"body","text":"A calm, science-backed formula designed for real routines and real results."},{"role":"cta","text":"Learn more"}],"image_zones":[{"role":"primary_visual","zone_id":"image","required":true}],"logo_rules":{"zone_id":"logo","required":false},"cta_placement":{"alignment":"left"},"platform_preset":"linkedin","export_format":"png","overflow_strategy":{"mode":"shrink_then_wrap"}}'::jsonb,
    '{"retrieval_channels":["brand","strategy"],"providers":{"research":"anthropic","generation":"openai","image":"mock"},"context_resolution":{"priority_order":["guardrails","identity","foundations","voice_tone","visual_identity","prompt_intelligence","persona_context","objective_context","strategy","brand","campaign_history","template","metadata","user_prompt"]}}'::jsonb,
    88,
    '{"score":88,"matched_signals":["clear","warm"],"deviations":[],"rewrite_suggestions":["Add one proof point if needed"]}'::jsonb,
    NULL
) ON CONFLICT (id) DO NOTHING;

INSERT INTO chat_messages (
    id,
    tenant_id,
    brand_space_id,
    session_id,
    user_id,
    content_version_id,
    role,
    message_text,
    structured_payload,
    citations
) VALUES
(
    'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeee1',
    '11111111-1111-1111-1111-111111111111',
    '66666666-6666-6666-6666-666666666666',
    'cccccccc-cccc-cccc-cccc-cccccccccccc',
    '33333333-3333-3333-3333-333333333333',
    NULL,
    'user',
    'Create a launch post for our serum',
    '{"studio_panel":{"format":"static","platform_preset":"linkedin","file_type":"png","size":{"width":1200,"height":627}}}'::jsonb,
    '[]'::jsonb
),
(
    'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeee2',
    '11111111-1111-1111-1111-111111111111',
    '66666666-6666-6666-6666-666666666666',
    'cccccccc-cccc-cccc-cccc-cccccccccccc',
    NULL,
    'dddddddd-dddd-dddd-dddd-dddddddddddd',
    'assistant',
    'Meet Your New Daily Serum

A calm, science-backed formula designed for real routines and real results.

Learn more',
    '{"content_version_id":"dddddddd-dddd-dddd-dddd-dddddddddddd"}'::jsonb,
    '[{"channel":"brand"},{"channel":"strategy"}]'::jsonb
)
ON CONFLICT (id) DO NOTHING;

INSERT INTO review_links (
    id,
    tenant_id,
    brand_space_id,
    content_version_id,
    created_by,
    token,
    title,
    status,
    allow_external_comments,
    expires_at
) VALUES (
    'ffffffff-ffff-ffff-ffff-ffffffffffff',
    '11111111-1111-1111-1111-111111111111',
    '66666666-6666-6666-6666-666666666666',
    'dddddddd-dddd-dddd-dddd-dddddddddddd',
    '33333333-3333-3333-3333-333333333333',
    'sample-review-link-token',
    'Launch Post Review',
    'pending',
    TRUE,
    NULL
) ON CONFLICT (id) DO NOTHING;

INSERT INTO usage_consumption (
    id,
    tenant_id,
    metric_code,
    period_key,
    consumed,
    metadata_json
) VALUES
(
    '12121212-1212-1212-1212-121212121212',
    '11111111-1111-1111-1111-111111111111',
    'users',
    TO_CHAR(CURRENT_DATE, 'YYYY-MM'),
    1,
    '{}'::jsonb
),
(
    '13131313-1313-1313-1313-131313131313',
    '11111111-1111-1111-1111-111111111111',
    'brand_spaces',
    TO_CHAR(CURRENT_DATE, 'YYYY-MM'),
    1,
    '{}'::jsonb
),
(
    '14141414-1414-1414-1414-141414141414',
    '11111111-1111-1111-1111-111111111111',
    'content_generations',
    TO_CHAR(CURRENT_DATE, 'YYYY-MM'),
    1,
    '{}'::jsonb
)
ON CONFLICT DO NOTHING;

COMMIT;
