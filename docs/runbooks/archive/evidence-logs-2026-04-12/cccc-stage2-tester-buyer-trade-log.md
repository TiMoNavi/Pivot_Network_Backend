# CCCC Stage2 Tester Buyer Trade Log

更新时间：`2026-04-11 05:05:07 CST` (`2026-04-10 21:05:07 UTC`)

## Scope

- 只服务于 `Stage2`
- 只验证真实 buyer trade path：
  - buyer 注册
  - buyer 登录
  - 浏览真实非 seed `listed` offer
  - 创建订单
  - 激活订单
  - 记录 grant 返回结果
- 不进入 `RuntimeSession`
- 不进入 `Buyer_Client` 实现

## Real Offer Under Test

- `offer_id = offer_76fff26fa2692634`
- `title = Medium GPU Runtime (compute-user-8b7c0b9dd725cbc3)`
- `status = listed`
- `seller_user_id = user_8b7c0b9dd725cbc3`
- `compute_node_id = compute-user-8b7c0b9dd725cbc3`
- `assessment_status = sellable`
- `published_at = 2026-04-10T20:54:08.712325Z`

## Canonical Evidence Run

### Action 1: buyer registration on the live backend

- Before state:
  - 本轮选用一个新的 buyer email：
    - `stage2-buyer-a341c1804963@example.com`
  - 本轮尚未创建该 buyer 账号
- Command:

```http
POST https://pivotcompute.store/api/v1/auth/register
Content-Type: application/json

{
  "email": "stage2-buyer-a341c1804963@example.com",
  "display_name": "Stage2 Buyer",
  "password": "Stage2Pass123",
  "role": "buyer"
}
```

- After state:
  - `201 Created`
  - returned user:
    - `id = user_13e35642ec9f9f57`
    - `email = stage2-buyer-a341c1804963@example.com`
    - `role = buyer`
    - `status = active`
  - returned auth session:
    - `token_type = bearer`
    - `expires_at = 2026-04-11T09:03:26.148093Z`
- Rollback:
  - none from current public API surface
- What this verified:
  - live buyer registration works on the active backend

### Action 2: buyer login and auth check

- Before state:
  - buyer `stage2-buyer-a341c1804963@example.com` exists and is active
- Command:

```http
POST https://pivotcompute.store/api/v1/auth/login
Content-Type: application/json

{
  "email": "stage2-buyer-a341c1804963@example.com",
  "password": "Stage2Pass123"
}
```

  - auth check:

```http
GET https://pivotcompute.store/api/v1/auth/me
Authorization: Bearer <login access_token>
```

- After state:
  - `POST /auth/login -> 200`
  - returned user:
    - `id = user_13e35642ec9f9f57`
    - `email = stage2-buyer-a341c1804963@example.com`
    - `role = buyer`
    - `status = active`
  - returned auth session:
    - `token_type = bearer`
    - `expires_at = 2026-04-11T09:04:17.118318Z`
  - `GET /auth/me -> 200`
  - `auth/me` returned the same buyer identity
- Rollback:

```http
POST https://pivotcompute.store/api/v1/auth/logout
Authorization: Bearer <login access_token>
```

- What this verified:
  - live buyer login works
  - login token is valid for subsequent buyer-side trade calls

### Action 3: visible real non-seed listed offer

- Before state:
  - Stage1 has already produced a real non-seed `listed` offer
- Command:

```http
GET https://pivotcompute.store/api/v1/offers
```

- After state:
  - `200 OK`
  - live `/offers` returned exactly one real non-seed listed offer:
    - `offer_id = offer_76fff26fa2692634`
    - `status = listed`
    - `seller_user_id = user_8b7c0b9dd725cbc3`
    - `compute_node_id = compute-user-8b7c0b9dd725cbc3`
    - `runtime_image_ref = registry.example.com/pivot/runtime:python-gpu-v1`
    - `inventory_state.assessment_status = sellable`
    - `price_snapshot.hourly_price = 12.5`
- Rollback:
  - none; read-only
- What this verified:
  - buyer can see the real non-seed listed offer created in Stage1

### Action 4: order creation using the login-backed buyer token

- Before state:
  - buyer login token is valid
  - target offer is visible and `listed`
- Command:

```http
POST https://pivotcompute.store/api/v1/orders
Authorization: Bearer <login access_token>
Content-Type: application/json

{
  "offer_id": "offer_76fff26fa2692634",
  "requested_duration_minutes": 60
}
```

- After state:
  - `201 Created`
  - returned order:
    - `id = order_5d1236d1338ac6ab`
    - `buyer_user_id = user_13e35642ec9f9f57`
    - `offer_id = offer_76fff26fa2692634`
    - `status = created`
    - `requested_duration_minutes = 60`
    - `runtime_bundle_status = placeholder_pending`
    - `access_grant_id = null`
- Rollback:
  - none from current public API surface
- What this verified:
  - buyer can create an order against the real listed offer

### Action 5: order activation and grant issuance

- Before state:
  - `order_5d1236d1338ac6ab` exists with:
    - `status = created`
    - `access_grant_id = null`
- Command:

```http
POST https://pivotcompute.store/api/v1/orders/order_5d1236d1338ac6ab/activate
Authorization: Bearer <login access_token>
```

  - post-activation grant readback:

```http
GET https://pivotcompute.store/api/v1/me/access-grants/active
Authorization: Bearer <login access_token>
```

  - downloaded grant artifact:

```http
GET https://pivotcompute.store/api/v1/files/download/generated/access-grants/grant_a84b49a685609153.json
```

- After state:
  - `POST /orders/order_5d1236d1338ac6ab/activate -> 200`
  - activated order:
    - `status = grant_issued`
    - `access_grant_id = grant_a84b49a685609153`
  - returned access grant:
    - `id = grant_a84b49a685609153`
    - `status = issued`
    - `grant_type = placeholder`
    - `expires_at = 2026-04-11T09:04:17.474765Z`
    - `runtime_session_id = placeholder-runtime-338ac6ab`
    - `connect_material_payload.join_session_id = join_session_733b69e1bf293c7a`
    - `connect_material_payload.effective_target_addr = 10.66.66.10`
    - `connect_material_payload.raw_manager_acceptance_status = matched`
  - `GET /me/access-grants/active -> 200`
    - latest grant is the same `grant_a84b49a685609153`
  - downloaded artifact `generated/access-grants/grant_a84b49a685609153.json` contains:
    - `id = grant_a84b49a685609153`
    - `expires_at = 2026-04-11T09:04:17.474765+00:00`
    - no `grant_code` field
- Rollback:
  - none from current public API surface
- What this verified:
  - live backend issues a real persisted `AccessGrant` on activation
  - live backend returns a real `grant_id` and `expires_at`
  - current live activation/grant path still does **not** expose a `grant_code` in:
    - activation response
    - active grants list
    - downloaded grant artifact

## Stage2 Result From Tester Side

- Verified:
  - buyer registration works
  - buyer login works
  - buyer can see the real non-seed listed offer
  - buyer can create an order on that offer
  - buyer can activate the order and receive a real persisted grant
- Verified returned grant payload facts:
  - `grant_id = grant_a84b49a685609153`
  - `expires_at = 2026-04-11T09:04:17.474765Z`
- Verified gap:
  - `grant_code` is not present in the current live returned payload path

## Appendix

- An earlier exploratory run in the same session also succeeded using the register-issued token:
  - `order_id = order_bf613fbd09322f43`
  - `grant_id = grant_e9026765bf8e45a1`
- The canonical Stage2 evidence above uses the explicit login-backed order/grant path:
  - `order_id = order_5d1236d1338ac6ab`
  - `grant_id = grant_a84b49a685609153`
