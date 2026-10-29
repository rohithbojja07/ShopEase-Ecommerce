from django.shortcuts import render


def analytics_dashboard_page(request):
    return render(request, "admin/analytics_dashboard.html")
