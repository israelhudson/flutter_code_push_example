-- Dedicated POC only; indexes for foreign keys reported by Supabase advisors.
create index poc_adjustment_tokens_candidate_id_idx on public.poc_adjustment_tokens(candidate_id);
create index poc_candidates_business_reviewer_idx on public.poc_candidates(business_reviewer);
create index poc_candidates_creator_github_idx on public.poc_candidates(creator_github);
create index poc_candidates_creator_slack_idx on public.poc_candidates(creator_slack);
create index poc_candidates_previous_candidate_idx on public.poc_candidates(previous_candidate);
create index poc_candidates_technical_reviewer_idx on public.poc_candidates(technical_reviewer);
create index poc_config_business_reviewer_idx on public.poc_config(business_reviewer);
create index poc_config_operator_github_idx on public.poc_config(operator_github);
create index poc_config_technical_reviewer_idx on public.poc_config(technical_reviewer);
create index poc_events_candidate_id_idx on public.poc_events(candidate_id);
