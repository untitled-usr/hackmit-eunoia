use poem_openapi::Tags;

#[derive(Tags)]
#[allow(dead_code)]
pub enum ApiTags {
    /// Token operations
    Token,

    /// User operations
    User,

    /// Group operations
    Group,

    /// Message operations
    Message,

    /// Resource operations
    Resource,

    /// Favorite archive operations
    Favorite,

    /// License operations
    License,

    /// User management operations
    AdminUser,

    /// System management operations
    AdminSystem,

    /// Agora management operations
    AdminAgora,

    /// Firebase management operations
    AdminFirebase,

    /// Smtp management operations
    AdminSmtp,

    /// Bot operations
    Bot,
}
