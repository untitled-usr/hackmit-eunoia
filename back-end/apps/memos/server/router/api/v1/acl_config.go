package v1

// PublicMethods defines API endpoints that don't require X-Acting-Uid.
// All other endpoints require a valid X-Acting-Uid header.
//
// This is the SINGLE SOURCE OF TRUTH for public endpoints.
// Both Connect interceptor and gRPC-Gateway interceptor use this map.
//
// Format: Full gRPC procedure path as returned by req.Spec().Procedure (Connect)
// or info.FullMethod (gRPC interceptor).
var PublicMethods = map[string]struct{}{
	// Instance Service - instance info before acting user is chosen
	"/memos.api.v1.InstanceService/GetInstanceProfile": {},
	"/memos.api.v1.InstanceService/GetInstanceSetting": {},

	// User Service - public user profiles and stats
	"/memos.api.v1.UserService/CreateUser":       {}, // Public USER registration (builtin admin exists after migrate)
	"/memos.api.v1.UserService/GetUser":          {},
	"/memos.api.v1.UserService/GetUserAvatar":    {},
	"/memos.api.v1.UserService/GetUserStats":     {},
	"/memos.api.v1.UserService/ListAllUserStats": {},
	"/memos.api.v1.UserService/SearchUsers":      {},

	// Identity Provider Service - public list (admin-only mutations still require X-Acting-Uid)
	"/memos.api.v1.IdentityProviderService/ListIdentityProviders": {},

	// Memo Service - public memos (visibility filtering done in service layer)
	"/memos.api.v1.MemoService/GetMemo":          {},
	"/memos.api.v1.MemoService/ListMemos":        {},
	"/memos.api.v1.MemoService/ListMemoComments": {},
}

// IsPublicMethod checks if a procedure path is public (no X-Acting-Uid required).
// Returns true for public methods, false for protected methods.
func IsPublicMethod(procedure string) bool {
	_, ok := PublicMethods[procedure]
	return ok
}
