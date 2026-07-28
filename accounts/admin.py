from django.contrib import admin

from .models import CustomUser, SecurityQuestion


@admin.register(CustomUser)
class CustomUserAdmin(admin.ModelAdmin):
    """Admin configuration for CustomUser model."""
    list_display = ("email", "username", "full_name", "role", "is_active", "date_joined")
    list_filter = ("role", "is_active", "is_staff")
    search_fields = ("email", "username", "full_name")
    ordering = ("-date_joined",)
    readonly_fields = ("date_joined",)


@admin.register(SecurityQuestion)
class SecurityQuestionAdmin(admin.ModelAdmin):
    """Admin configuration for SecurityQuestion model."""
    list_display = ("user", "question_display", "created_at")
    list_filter = ("question",)
    search_fields = ("user__email", "user__full_name", "question")
    readonly_fields = ("hashed_answer", "created_at", "updated_at")

    def question_display(self, obj):
        """Return the human-readable question text."""
        return obj.get_question_display()
    question_display.short_description = "Security Question"
