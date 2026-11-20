// Shared by live stores and v3 recovery. Changes require a migration and restore tests.
export const STORE_SCHEMAS={
 library:{name:'cj-music-library-v1',version:2,stores:['state','research_jobs','research_nodes','research_edges','research_sources']},
 concepts:{name:'cj-concept-matching-v1',version:1,stores:['contexts','overrides']},
 exploration:{name:'cj-music-exploration-v1',version:1,stores:['state','cache']}
};
