# ShopEase API Reference

Base URL: http://127.0.0.1:8000

## Authentication
- /api/auth/login/
- /api/auth/token/refresh/
- /api/auth/register/
- /api/auth/logout/
- /api/auth/profile/
- /api/auth/change-password/

## Products
- /api/products/
- /api/categories/
- /api/brands/

## Cart and Wishlist
- /api/cart/
- /api/cart/add/
- /api/cart/update/
- /api/cart/remove/
- /api/cart/coupon/
- /api/coupons/validate/
- /api/wishlist/
- /api/wishlist/add/
- /api/wishlist/remove/
- /api/wishlist/move-to-cart/

## Orders, Returns and Payments
- /api/orders/
- /api/returns/
- /api/payment/create/
- /api/payment/verify/

## Staff and Inventory
- /api/admin/products/
- /api/admin/inventory/
- /api/admin/orders/
- /api/admin/returns/
- /api/admin/customers/
- /api/admin/audit-logs/
- /api/admin/reviews/

## Analytics
- /api/admin/analytics/dashboard/
- /api/admin/analytics/sales/
- /api/admin/analytics/products/
- /api/admin/analytics/customers/
- /api/admin/analytics/top-products/
- /api/admin/analytics/order-status/

## Other
- /api/addresses/
- /api/checkout/shipping-options/
- /api/checkout/summary/
- /api/notifications/
- /api/reviews/
- /api/health/

Verify HTTP methods, permissions, request fields and response formats in the corresponding Django views, viewsets, serializers and routers. This is a route overview, not a complete API specification. Never commit secrets or real .env files.
