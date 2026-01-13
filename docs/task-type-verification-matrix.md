# Task-Type Verification Matrix

## Overview

This document defines the verification strategy for different types of tasks in YokeFlow 2. By correctly identifying task types and applying appropriate verification methods, we can:

- **Reduce verification time by 30-40%** (avoiding unnecessary browser tests for config tasks)
- **Improve quality** by ensuring UI tasks always get visual verification
- **Catch more bugs** by using task-specific test strategies

## Task Type Detection

The system analyzes task descriptions to automatically categorize tasks into one of five types:

### 1. UI Tasks
**Keywords:** `ui`, `component`, `page`, `form`, `button`, `display`, `layout`, `style`, `view`, `render`, `frontend`, `react`, `vue`, `angular`, `modal`, `dialog`, `menu`, `navigation`, `sidebar`, `header`, `footer`, `card`, `list`, `table`, `grid`, `dashboard`

**Examples:**
- "Create login form component"
- "Build dashboard page with charts"
- "Implement responsive navigation menu"
- "Style the user profile card"

### 2. API Tasks
**Keywords:** `api`, `endpoint`, `route`, `middleware`, `server`, `rest`, `graphql`, `webhook`, `controller`, `handler`, `request`, `response`, `http`, `fastapi`, `express`, `flask`, `auth`

**Examples:**
- "Create REST API endpoint for user registration"
- "Implement authentication middleware"
- "Build GraphQL resolver for product queries"
- "Set up webhook handler for payment events"

### 3. Database Tasks
**Keywords:** `database`, `schema`, `table`, `migration`, `model`, `query`, `orm`, `sql`, `postgres`, `mysql`, `mongodb`, `redis`, `column`, `index`, `foreign key`, `constraint`, `relationship`

**Examples:**
- "Create users database table"
- "Add migration for order history"
- "Define ORM models for products"
- "Set up database connection pool"

### 4. Configuration Tasks
**Keywords:** `config`, `setup`, `typescript`, `build`, `package`, `dependencies`, `tooling`, `webpack`, `vite`, `rollup`, `eslint`, `prettier`, `jest`, `docker`, `environment`, `initialization`, `scaffold`, `boilerplate`, `install`

**Examples:**
- "Initialize TypeScript configuration"
- "Set up build pipeline with Webpack"
- "Configure ESLint and Prettier"
- "Install project dependencies"

### 5. Integration Tasks
**Keywords:** `workflow`, `end-to-end`, `e2e`, `user journey`, `full stack`, `complete flow`, `integration`, `connect`, `combine`

**Examples:**
- "Implement complete authentication flow"
- "Build end-to-end checkout process"
- "Create full user onboarding workflow"
- "Connect frontend to backend API"

## Verification Matrix

| Task Type | Primary Verification | Secondary Verification | Time Estimate | Tools Used |
|-----------|---------------------|----------------------|---------------|------------|
| **UI** | Browser (Playwright) | Unit tests for logic | 3-5 min | `browser_navigate`, `browser_snapshot`, `browser_click`, screenshots |
| **API** | API tests (curl/httpx) | Unit tests for handlers | 1-2 min | `bash_docker` with curl, HTTP status checks, JSON validation |
| **Database** | SQL queries | Integration tests | 1-2 min | Database connection tests, schema validation, CRUD operations |
| **Configuration** | Build verification | Linting | 30 sec | `bash_docker` with tsc/npm build, compilation checks |
| **Integration** | E2E Browser tests | API + Database tests | 5-10 min | Full Playwright workflows, multiple system checks |

## Test Generation Rules

### UI Tasks → Browser Tests (REQUIRED)
```python
test_types = [GeneratedTestType.BROWSER]
# Also add unit tests if there's business logic
if has_logic_files:
    test_types.append(GeneratedTestType.UNIT)
```

**Why:** UI bugs are visual and interaction-based. Only browser tests can verify:
- Components render correctly
- User interactions work
- Responsive design functions
- Accessibility features operate

### API Tasks → API Tests (Primary)
```python
test_types = [GeneratedTestType.API, GeneratedTestType.UNIT]
```

**Why:** API functionality is best tested through HTTP requests:
- Endpoint availability
- Request/response validation
- Status codes
- Error handling

### Database Tasks → Database Tests
```python
test_types = [GeneratedTestType.DATABASE, GeneratedTestType.INTEGRATION]
```

**Why:** Database changes need schema and data flow verification:
- Table/column existence
- Constraint validation
- Query performance
- Data integrity

### Configuration Tasks → Build Tests
```python
test_types = [GeneratedTestType.BUILD]
if has_logic:
    test_types.append(GeneratedTestType.UNIT)
```

**Why:** Config tasks need compilation/build verification:
- TypeScript compiles
- Dependencies install
- Build scripts succeed
- Linting passes

### Integration Tasks → E2E Tests
```python
test_types = [GeneratedTestType.E2E, GeneratedTestType.BROWSER]
```

**Why:** Full workflows need complete system testing:
- Multi-step user journeys
- Cross-system data flow
- Error recovery
- State management

## Time Savings Analysis

### Before Task-Type Awareness
- **Config task with browser test:** 5-10 minutes (unnecessary)
- **Database task with browser test:** 5-10 minutes (unnecessary)
- **UI task without browser test:** Bugs slip through

### After Task-Type Awareness
- **Config task with build test:** 30 seconds ✅ (90% faster)
- **Database task with SQL test:** 1 minute ✅ (80% faster)
- **UI task with browser test:** 3-5 minutes ✅ (catches visual bugs)

### Estimated Session Time Reduction
For a typical 30-task project:
- 10 UI tasks × 5 min = 50 minutes (unchanged, but necessary)
- 8 API tasks × 2 min = 16 minutes (vs 40 min with browser)
- 6 Config tasks × 0.5 min = 3 minutes (vs 30 min with browser)
- 4 Database tasks × 1 min = 4 minutes (vs 20 min with browser)
- 2 Integration tasks × 8 min = 16 minutes (unchanged)

**Total: 89 minutes vs 156 minutes = 43% reduction**

## Implementation Status

### ✅ Completed (Phase 3)
1. Added `TaskType` enum to `test_generator.py`
2. Implemented `_infer_task_type()` method with keyword analysis
3. Created `_determine_test_types_for_task()` method for type-based test selection
4. Added `GeneratedTestType.BUILD` and `GeneratedTestType.DATABASE` test types
5. Implemented `_generate_build_tests()` and `_generate_database_tests()` methods
6. Created test templates for build and database verification

### 🔄 Integration Points
- `AutoTestGenerator.generate_tests_for_task()` now uses task type inference
- `TaskVerifier` automatically benefits from improved test selection
- Logging added to track task type inference decisions

### 📊 Metrics to Track
- Test execution time per task type
- False positive rate (tests passing when they shouldn't)
- False negative rate (tests failing incorrectly)
- Task completion time reduction
- Bug escape rate by task type

## Usage in Coding Sessions

When the coding agent works on a task:

1. **Task description is analyzed** → Task type inferred
2. **Appropriate tests generated** → No wasted browser tests for config
3. **Verification runs faster** → 30-40% time savings
4. **Quality maintained** → UI tasks still get full browser verification

## Future Enhancements

1. **Machine Learning:** Train a classifier on historical task descriptions for better accuracy
2. **Custom Rules:** Allow projects to define their own task type keywords
3. **Hybrid Testing:** Smart combination of test types for complex tasks
4. **Performance Profiling:** Track actual time savings per project
5. **Feedback Loop:** Learn from verification failures to improve categorization

## Conclusion

Task-type aware verification ensures:
- ✅ Right test for the right task
- ✅ Faster verification cycles
- ✅ Better bug detection
- ✅ Reduced agent session time
- ✅ Improved developer experience

This is a key component of the YokeFlow 2 quality improvement initiative.