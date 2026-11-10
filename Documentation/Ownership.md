# Project Tasks & Ownership

## 1. Data Exploration & Preprocessing

**Owner: Prisha Goyal**

- [ ] Retrieve USDA FoodData Central records.
- [ ] Extract relevant food metadata and nutrient information.
- [ ] Clean and standardize food descriptions.
- [ ] Rename nutrient columns to consistent names.
- [ ] Handle missing nutrient values.
- [ ] Validate required columns and data types.
- [ ] Check for duplicate USDA food IDs.
- [ ] Generate `clean_usda_foods.csv`.
- [ ] Evaluate cleaned food records and document preprocessing decisions.

## 2. Ingredient Matching

**Owner: Prisha Goyal**

- [ ] Implement keyword-based ingredient matching.
- [ ] Develop ingredient normalization and alias handling.
- [ ] Implement candidate ranking and similarity scoring.
- [ ] Add penalties for prepared foods and compound dishes when appropriate.
- [ ] Prioritize relevant USDA food data types.
- [ ] Improve matching for ambiguous ingredients and preparation methods.
- [ ] Evaluate matching accuracy using representative test cases.
- [ ] Integrate semantic retrieval with the existing matching pipeline.
- [ ] Compare keyword-based and embedding-based retrieval.
- [ ] Handle cases where no suitable food match is found.

## 3. Seed Database

**Owner: Asha Thomas**

- [ ] Build and maintain the local recipe seed database.
- [ ] Organize recipe information into consistent data structures.
- [ ] Validate recipe ingredients and quantities.
- [ ] Prepare recipe data for retrieval and orchestrator integration.

## 4. SQL & Vector Database

**Owner: Prisha Goyal**

- [ ] Set up PostgreSQL using Docker.
- [ ] Create the project database.
- [ ] Enable the pgvector extension.
- [ ] Design and create the database schema.
- [ ] Create the USDA foods table.
- [ ] Import cleaned USDA food records into PostgreSQL.
- [ ] Verify imported records and nutrient values.
- [ ] Evaluate and select an embedding model.
- [ ] Generate embeddings for USDA food descriptions.
- [ ] Create a vector storage table.
- [ ] Store embeddings using pgvector.
- [ ] Implement vector similarity search.
- [ ] Evaluate retrieval results and similarity thresholds.
- [ ] Integrate vector search with ingredient matching.
- [ ] Document database setup and usage.

## 5. Macro Calculator

**Owner: Chandana Robba**

- [ ] Implement deterministic ingredient-level macro calculations.
- [ ] Calculate recipe-level and meal-level nutrient totals.
- [ ] Support ingredient quantities and gram conversions.
- [ ] Validate calculations against USDA nutrient data.
- [ ] Tune the macro calculator for accuracy.
- [ ] Evaluate macro calculation variance.
- [ ] Support macro verification for generated meal plans.

## 6. Orchestrator Agent

**Owner: Trang Hoang**

- [ ] Design the multi-agent orchestration architecture.
- [ ] Implement the Planner, Retriever, and Math Verifier agents.
- [ ] Define agent responsibilities and communication.
- [ ] Integrate recipe retrieval and macro calculation tools.
- [ ] Implement tool-calling workflows.
- [ ] Verify that mathematical calculations are handled by deterministic tools rather than LLM-generated arithmetic.
- [ ] Implement error recovery for failed tool calls and missing data.

## 7. Recipe Retrieval

**Owner: TBD**

- [ ] Implement recipe retrieval from the local seed database.
- [ ] Integrate semantic recipe retrieval.
- [ ] Support filtering based on dietary restrictions and user preferences.
- [ ] Rank retrieved recipes based on relevance.
- [ ] Integrate recipe retrieval with the orchestrator.

## 8. Frontend & Application Integration

**Owner: Chandana Robba**

- [ ] Develop the interactive Streamlit application.
- [ ] Build user input interfaces for dietary restrictions and macro targets.
- [ ] Display generated meal plans.
- [ ] Display daily and meal-level macro totals.
- [ ] Show macro calculation verification results.
- [ ] Integrate the frontend with the orchestrator and backend components.
- [ ] Support displaying 7-day meal plans.

## 9. Testing & Validation

**Owner: TBD**

- [ ] Define evaluation benchmarks for macro calculation variance.
- [ ] Evaluate meal plan compliance with nutritional targets.
- [ ] Test ingredient matching accuracy.
- [ ] Test vector retrieval quality.
- [ ] Test multi-agent tool-calling workflows.
- [ ] Test API timeouts and missing USDA records.
- [ ] Validate error recovery and fallback behavior.
- [ ] Run end-to-end tests on generated meal plans.
- [ ] Document evaluation results.

## 10. Documentation & Final Deliverables

**Owner: All Team Members**

- [ ] Maintain documentation for individual components.
- [ ] Document system architecture and data flow.
- [ ] Prepare setup instructions for the GitHub repository.
- [ ] Ensure code is modular and organized.
- [ ] Finalize evaluation reports.
- [ ] Prepare the stakeholder presentation deck.

---

## Ownership Tracking

| Team Member | Primary Responsibility |
|---|---|
| Prisha Goyal | Data exploration, preprocessing, ingredient matching, SQL & vector database |
| Asha Thomas | Seed database and Orchestrator agent|
| Trang Hoang | Orchestrator agent|
| Chandana Robba | Macro calculator |
| TBD | Recipe retrieval, frontend integration, testing & validation |

## Project Milestones

| Month | Milestone | Key Deliverables |
|---|---|---|
| September | Architecture, Data Pipelines & Deterministic Baseline | Structured recipe seed database, USDA API integration, Pydantic validation, deterministic macro calculator, evaluation benchmarks |
| October | Multi-Agent Orchestration & Constraint Scaling Engine | Multi-agent state graph, dynamic ingredient scaling, PostgreSQL/pgvector semantic retrieval, tool-calling validation |
| November / December | System Resiliency, UI Deployment & Capstone Deliverables | Error-recovery workflows, interactive Streamlit application, 7-day meal plans, production-ready GitHub repository, documentation, evaluation reports, stakeholder presentation |
