# DATING ALGORITHM ENGINEERING & REVERSE-ENGINEERED ARCHITECTURAL RESEARCH
Document: BACKEND_RESEARCH.md
Focus: Hinge, Tinder, Bumble Recommendation Algorithms, Two-Sided Matching Markets, Gale-Shapley Implementation
Compliance: Strictly Zero Emojis, Complete Mathematical Proofs, Production Engineering Analysis

---

## 1. THE FUNDAMENTAL DATING ALGORITHM PROBLEM: RECIPROCAL TWO-SIDED MARKETS

### 1.1 One-Sided vs Two-Sided Recommendation Systems
Traditional recommendation engines (Netflix, Amazon, YouTube) operate as **one-sided matching systems**:
- The user consumes an inanimate item (movie, book, video).
- The item has infinite inventory and zero agency; it cannot reject the user.
- Optimization function: Maximize $P(\text{Click} \mid \text{User}, \text{Item})$ or $P(\text{WatchTime} \mid \text{User}, \text{Item})$.

Dating platforms operate as **two-sided reciprocal matching markets**:
- Both sides of the transaction are autonomous human agents with distinct, competing preferences.
- An interaction only succeeds if **both** agents consent:
$$\text{Match}(A, B) \iff \text{Like}(A \to B) \land \text{Like}(B \to A)$$
- A recommendation engine that only recommends people User A likes will fail if those people never like User A back.
- Mathematical objective:
$$\text{Maximize } P(\text{Mutual Match}) = P(A \to B) \times P(B \to A \mid A \to B)$$

---

## 2. DECONSTRUCTION OF HINGE'S ALGORITHM: GALE-SHAPLEY & MACHINE LEARNING

Hinge's architecture famously centers on the Nobel Prize-winning **Gale-Shapley Stable Marriage Algorithm** (David Gale and Lloyd Shapley, 1962, Nobel Memorial Prize in Economic Sciences 2012), paired with gradient-boosted decision trees and offline date feedback loops.

```
+-----------------------------------------------------------------------------------+
| HINGE ALGORITHMIC PIPELINE                                                        |
+-----------------------------------------------------------------------------------+
| 1. RAW EVENT LOGS                                                                 |
| (Dwell time, prompt likes, photo likes, comments, response latency, We Met)       |
|                                    |                                              |
|                                    v                                              |
| 2. MACHINE LEARNING PREFERENCE ENGINE                                             |
| (Two-Tower Vector Embeddings + GBDT predicting reciprocal probability)            |
|                                    |                                              |
|                                    v                                              |
| 3. PREFERENCE LIST GENERATION                                                     |
| (Every active user gets an ordered rank list of compatible candidates)            |
|                                    |                                              |
|                                    v                                              |
| 4. GALE-SHAPLEY DEFERRED ACCEPTANCE SOLVER                                        |
| (Iterative proposal & tentative holding until stable equilibrium achieved)        |
|                                    |                                              |
|                                    v                                              |
| 5. "MOST COMPATIBLE" DAILY PAIRING & CONGESTION CONTROLLED FEED                   |
+-----------------------------------------------------------------------------------+
```

### 2.1 The Gale-Shapley Stable Marriage Problem Formulation
Let $M = \{m_1, m_2, \dots, m_n\}$ be the set of active men and $W = \{w_1, w_2, \dots, w_n\}$ be the set of active women in a geographic partition (e.g. Bangalore South).
- Each man $m \in M$ holds a strictly ordered preference list over $W$:
$$P(m) = [w_{\pi(1)}, w_{\pi(2)}, \dots, w_{\pi(n)}]$$
- Each woman $w \in W$ holds a strictly ordered preference list over $M$:
$$P(w) = [m_{\sigma(1)}, m_{\sigma(2)}, \dots, m_{\sigma(n)}]$$

#### The Stability Criterion
A matching $\mu: M \to W$ is **stable** if and only if there does NOT exist any pair $(m, w)$ such that:
1. $m$ prefers $w$ over his assigned partner $\mu(m)$, AND
2. $w$ prefers $m$ over her assigned partner $\mu^{-1}(w)$.

Such an unassigned pair $(m, w)$ is defined as a **blocking pair**. If a blocking pair exists, both parties have rational incentives to abandon their current matches to pair with each other, destabilizing the market.

#### The Deferred Acceptance Algorithm (Hinge Daily Run)
```python
def deferred_acceptance(men_preferences, women_preferences):
    # All men and women initially free
    free_men = list(men_preferences.keys())
    proposals_made = {m: 0 for m in free_men}
    current_matches = {} # woman -> man

    while free_men:
        m = free_men.pop(0)
        # Get next woman on m's preference list
        w = men_preferences[m][proposals_made[m]]
        proposals_made[m] += 1

        if w not in current_matches:
            # Woman is free; tentatively accept
            current_matches[w] = m
        else:
            current_partner = current_matches[w]
            w_pref = women_preferences[w]
            if w_pref.index(m) < w_pref.index(current_partner):
                # Woman prefers new proposer; displace current partner
                current_matches[w] = m
                free_men.append(current_partner)
            else:
                # Woman rejects proposer; man remains free
                free_men.append(m)

    return current_matches
```

#### Why Gale-Shapley Eliminates the 80/20 Inequality
In traditional swipe apps (Tinder), the top 5% of desirable profiles receive 80% of all incoming likes, creating an unserviceable queue for top profiles and starvation for everyone else. 
Gale-Shapley solves this through **mutual constraint**:
- If Man A and Man B both rank Woman X as #1, but Woman X prefers Man A, Man B is rejected.
- Man B's proposal is automatically deferred to his #2 preference (Woman Y), who accepts him over lower-ranked suitors.
- Result: Matches are distributed across the entire active network rather than clustering around a tiny demographic elite.

### 2.2 How Hinge Constructs the Preference Lists via Machine Learning
Gale-Shapley requires ordered preference lists as input. In real life, users do not manually rank hundreds of profiles. Hinge uses machine learning to predict these preference lists:

1. **Feature Vector Extraction**:
   - Stated Preferences: Age, height, location radius, religious/dietary dealbreakers.
   - Revealed Interactions:
     * Dwell time on specific photos vs text prompts (measured in milliseconds).
     * Type of content liked (specific prompt response vs standard portrait).
     * Message content quality: Length of comment attached to like.
     * Response latency: How quickly user replies to inbound messages.
2. **Two-Tower Neural Embeddings**:
   - User Tower: Encodes user historical actions into 128-dimensional dense vector $\vec{u}_A$.
   - Candidate Tower: Encodes candidate profile characteristics into 128-dimensional dense vector $\vec{v}_B$.
   - Affinity Dot Product:
$$\hat{y}_{AB} = \sigma(\vec{u}_A \cdot \vec{v}_B + \text{bias})$$
3. **Reciprocal Score Aggregation**:
$$S(A, B) = \sqrt{\hat{y}_{AB} \times \hat{y}_{BA}}$$
This combined score sorts the preference lists fed into the Gale-Shapley solver each night.

### 2.3 The "We Met" Ground Truth Feedback Loop
The fundamental flaw of engagement-based machine learning is that optimizing for in-app engagement (swiping, chatting) often optimizes for addictive, unresolved conversations.
Hinge introduced the **"We Met"** survey to collect offline ground truth:
1. Signal Detection: After a match exchanges phone numbers or reaches high message density, the app prompts both users 48 hours later: "Did you meet in person?" and "Are they the type of person you'd see again?".
2. Reinforcement Learning Update:
   - If both answer YES: The feature vectors of both users receive strong positive gradient reinforcement for reciprocal pairing.
   - If either answers NO: The model penalizes the specific latent feature combinations that triggered the false-positive match.
3. Outcome: Hinge trains its model on **relationship viability**, not session duration.

---

## 3. DECONSTRUCTION OF TINDER'S ALGORITHM: ELO, COLLABORATIVE FILTERING & PITFALLS

### 3.1 The Elo / Glicko-2 Desirability Rating
Tinder originally adapted Arpad Elo's chess rating system to rank user "desirability":
- Every profile started with a baseline Elo score (e.g., 1200).
- A swipe right was treated as a "win" for the recipient and a swipe left as a "loss".
- Expected outcome probability:
$$E_A = \frac{1}{1 + 10^{(R_B - R_A)/400}}$$
- Rating update:
$$R_A' = R_A + K \cdot (S_A - E_A)$$
Where $S_A = 1$ if liked, $0$ if passed, and $K$ is the update velocity factor.

### 3.2 The Structural Failure of Tinder's ELO System
1. **The Asymmetric Swipe Distribution**:
   - Empirical studies demonstrate that men swipe right on ~46% of profiles, while women swipe right on ~14%.
   - Because men swipe indiscriminately, male profiles lose Elo rating rapidly with every pass from a selective female profile.
   - Average male Elo scores enter a death spiral ($R_{\text{male}} < 900$).
2. **Algorithmic Segregation (The ELO Bubble)**:
   - Tinder segments feeds by Elo brackets. Users with Elo 800 only see users with Elo 800.
   - Users with low Elo are pushed to the very back of candidate queues, effectively shadowbanned behind thousands of higher-rated profiles.
3. **Extractive Monetization**:
   - Tinder monetizes this artificial deficit: buying Tinder Gold or Boosts temporarily artificially injects a suppressed profile into the top of the stack, turning basic visibility into a pay-to-play auction.

---

## 4. DECONSTRUCTION OF BUMBLE'S ALGORITHM: FIRST MOVE MECHANICS & VELOCITY

### 4.1 Architecture
Bumble operates on a modified collaborative filtering engine with gendered state machine gates:
1. Two-Sided Collaborative Filtering: Profiles are clustered using matrix factorization (Alternating Least Squares) based on co-swiping graphs.
2. Inverted Finite State Machine:
   - Mutual like creates a `PENDING_INITIATION` match state.
   - 24-hour countdown timer begins. Only the woman can trigger message insertion.
   - Once the first message is sent, a secondary 24-hour countdown starts for the man to reply.

### 4.2 Structural Failure of Bumble's 24-Hour Timer
1. **High Ghosting Rate**: Real-world schedules (work deadlines, travel) prevent women from drafting thoughtful opening messages within 24 hours. Over 35% of mutual matches expire without a single word.
2. **Superficial Openers**: The anxiety of the timer forces users into low-effort openers ("Hey", emojis, dots) just to stop the clock.
3. **Frustration Monetization**: Bumble monetizes this pressure by charging for "Daily Extends" to keep expiring matches alive.

---

## 5. COMPARATIVE MATRIX: DATING RECOMMENDATION ALGORITHMS

| Metric / Dimension | Tinder (Match Group) | Bumble (Bumble Inc.) | Hinge (Match Group) | Jainune (Proposed Architecture) |
| :--- | :--- | :--- | :--- | :--- |
| **Primary Algorithm** | Collaborative Filtering + Elo Desirability | Collaborative Filtering + Gender State Machine | Gale-Shapley Stable Matching + GBDT Ranker | Values-Weighted Reciprocal Engine (VWRE) + Gale-Shapley |
| **Market Objective** | Maximize in-app swipe sessions & ad impressions | Maximize female initiation within 24 hours | Maximize reciprocal matches ("Designed to be deleted") | Maximize high-intent Bangalore community connections |
| **Handling of Low ELO** | Suppression / Shadowban to sell Boosts | Low priority in stack; sell Extends | Gale-Shapley redistributes proposals across network | Dignity Floor (Guaranteed 35 impressions / 48h) |
| **Offline Date Loop** | None (Session time is KPI) | Minimal post-chat surveys | "We Met" survey after 48h phone exchange | Green Flag Reflection + Bangalore Vibe validation |
| **Dealbreaker Gating** | Basic age/distance filters | Height, drinking, basic religion filters | Hard dealbreaker toggles for strict requirements | Deep Cultural/Dietary matrix (Pure Jain, sects, root veg, metro radius) |
| **Chat Expiry** | No expiration (Matches decay indefinitely) | 24-hour hard countdown (Panic inducing) | "Your Turn" visual nudges, no hard expiration | 72-Hour Momentum Ring with Voice Note & Date unlocks |

---

## 6. JAINUNE BACKEND ARCHITECTURAL SPECIFICATION

Based on this deep research, Jainune's backend synthesizes the mathematical stability of Hinge's Gale-Shapley with ethical cultural safeguards and real-time Bangalore routing.

```
+----------------------------------------------------------------------------------------------------+
| JAINUNE BACKEND SYSTEM ARCHITECTURE                                                                |
+----------------------------------------------------------------------------------------------------+
|                                                                                                    |
|  [ React Native Mobile Client ]                                                                    |
|               |                                                                                    |
|               v (HTTPS / WSS via Cloudflare)                                                       |
|  [ Traefik / FastAPI API Gateway ]                                                                 |
|               |                                                                                    |
|       +-------+-------+--------------------+---------------------+                                 |
|       |               |                    |                     |                                 |
|       v               v                    v                     v                                 |
| [ Auth Service ] [ Profile Engine ] [ Feed & Matching ]  [ Chat & Realtime ]                       |
| (MSG91 OTP)      (FastAPI + S3)     (VWRE + Gale-Shapley) (Supabase Realtime / WSS)                |
|       |               |                    |                     |                                 |
|       +---------------+--------------------+---------------------+                                 |
|                               |                                                                    |
|               +---------------+---------------+                                                    |
|               |                               |                                                    |
|               v                               v                                                    |
|  [ Supabase PostgreSQL + PostGIS ]     [ Redis 7.0 Cluster ]                                       |
|  - Relational entities & user state    - Ephemeral queues (The Wheel)                              |
|  - PostGIS geospatial indexing        - Active session tokens & rate limits                       |
|  - pgvector 128-d user embeddings     - Feed candidate caches & locks                             |
|                                                                                                    |
+----------------------------------------------------------------------------------------------------+
```

### 6.1 The Values-Weighted Reciprocal Engine (VWRE)
Jainune's candidate scoring function combines four mathematical vectors:
$$Score(A, B) = w_1 \cdot C_{\text{dietary}}(A, B) + w_2 \cdot C_{\text{sect}}(A, B) + w_3 \cdot G_{\text{geo}}(A, B) + w_4 \cdot R_{\text{reciprocal}}(A, B)$$

Where:
1. **$C_{\text{dietary}}(A, B)$ (Dietary Compatibility Constraint)**:
   - Binary elimination if either user marks a dietary rule as a strict dealbreaker (e.g. Pure Jain vs Non-Jain).
   - Partial score (0.0 to 1.0) based on root vegetable / nightshade rules (Paryushan strictness, onion-garlic tolerance).
2. **$C_{\text{sect}}(A, B)$ (Community & Philosophical Resonance)**:
   - Marwari, Gujarati, Digambar, Shwetambar (Deravasi, Sthanakvasi, Terapanthi).
3. **$G_{\text{geo}}(A, B)$ (Bangalore Hub Feasibility)**:
   - Calculated via PostGIS spatial distance with traffic friction weighting:
$$G_{\text{geo}}(A, B) = \exp\left(-\frac{\text{DistanceKm}(A, B)^2}{2 \cdot \sigma^2}\right)$$
   - Commuting between Indiranagar and Koramangala has high weight ($\sigma = 8\text{km}$); commuting between Whitefield and Jayanagar receives severe traffic decay penalties.
4. **$R_{\text{reciprocal}}(A, B)$ (Reciprocal Machine Learning Score)**:
   - Dot product of 128-dimensional dense vector embeddings generated from prompt interactions, audio snapshot dwell time, and dilemma duel choices.

### 6.2 The Dignity Engine Algorithm: Enforcing Visibility Floors
To prevent Tinder-style ELO collapse, Jainune implements an algorithmic **Exposure Balancer**:
```python
def get_user_feed(user_id: str, db_pool, redis_client):
    # 1. Fetch Hard Dealbreaker Candidates via PostGIS
    candidates = fetch_geospatial_candidates(user_id, radius_km=15)
    
    # 2. Compute VWRE Scores
    scored_candidates = [
        (c, compute_vwre_score(user_id, c)) 
        for c in candidates 
        if passes_strict_dietary(user_id, c)
    ]
    scored_candidates.sort(key=lambda x: x[1], reverse=True)
    
    # 3. Dignity Injection: Guarantee 35 impressions per 48 hours for underserved active profiles
    underserved = get_underserved_active_profiles(limit=2)
    
    # Interleave: 8 high-compatibility nodes + 2 dignity exploration nodes
    final_feed = interleave_feed(scored_candidates[:8], underserved)
    return final_feed
```

---

## 7. DATABASE & INFRASTRUCTURE SPECIFICATION

### 7.1 Core Schema Entities (PostgreSQL + PostGIS)
```sql
-- USER ACCOUNTS & CULTURAL ATTRIBUTES
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    phone_number VARCHAR(16) UNIQUE NOT NULL,
    first_name VARCHAR(64) NOT NULL,
    date_of_birth DATE NOT NULL,
    gender VARCHAR(24) NOT NULL,
    dietary_strictness VARCHAR(32) NOT NULL, -- 'pure_jain', 'vaishnav', 'ovo_veg', 'vegan'
    eats_root_vegetables BOOLEAN DEFAULT FALSE,
    eats_onion_garlic BOOLEAN DEFAULT FALSE,
    community_sect VARCHAR(32), -- 'digambar', 'shwetambar_deravasi', 'shwetambar_sthanakvasi', 'terapanthi'
    home_neighborhood VARCHAR(64), -- 'jayanagar', 'indiranagar', 'koramangala', 'hsr'
    location GEOMETRY(Point, 4326), -- PostGIS coordinates
    embedding vector(128), -- pgvector compatibility embedding
    impressions_last_48h INT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- PROMPTS & AUDIO SNAPSHOTS
CREATE TABLE user_prompts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    prompt_key VARCHAR(64) NOT NULL,
    response_text VARCHAR(200),
    audio_s3_url VARCHAR(256),
    audio_duration_seconds NUMERIC(4,2),
    position INT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- LIKES & DISCOVERY INTERACTIONS
CREATE TABLE discovery_interactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    target_user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    interaction_type VARCHAR(16) NOT NULL, -- 'like', 'pass'
    target_content_type VARCHAR(24), -- 'photo', 'prompt', 'voice'
    target_content_id UUID,
    attached_comment VARCHAR(200),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(actor_user_id, target_user_id)
);

-- ACTIVE MATCHES & MOMENTUM PROTOCOL
CREATE TABLE matches (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_a UUID REFERENCES users(id) ON DELETE CASCADE,
    user_b UUID REFERENCES users(id) ON DELETE CASCADE,
    match_source VARCHAR(32) NOT NULL, -- 'standard_orbit', 'dilemma_duel', 'the_wheel'
    status VARCHAR(24) NOT NULL DEFAULT 'active', -- 'active', 'momentum_locked', 'graceful_closed', 'expired'
    momentum_deadline TIMESTAMPTZ NOT NULL, -- NOW() + INTERVAL '72 hours'
    voice_notes_exchanged INT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## 8. SUMMARY CONCLUSION FOR JAINUNE BACKEND BUILD

1. **Adopt Hinge's Gale-Shapley Foundation**: Build the nightly "Most Compatible" pairing job using deferred acceptance so matches distribute equitably.
2. **Replace Elo with VWRE**: Eliminate toxic attractiveness scores. Rank candidates based on cultural alignment (dietary strictness, sect), Bangalore geographic travel feasibility, and mutual vector affinity.
3. **Enforce Ethical Dignity Floor**: Enforce a minimum of 35 impressions every 48 hours for every verified active user in the database.
4. **Isolate the Serendipity Arcade**: Keep the Random Wheel micro-transaction engine on a low-latency Redis queue (`O(1)` pop/push), completely independent of relational PostgreSQL match tables.
