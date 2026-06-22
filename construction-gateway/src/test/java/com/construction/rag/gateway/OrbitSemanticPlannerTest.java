package com.construction.rag.gateway;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;

class OrbitSemanticPlannerTest {
  @Test
  void plansGroupCountByLogicalStatus() {
    OrbitSemanticPlanner planner = new OrbitSemanticPlanner();

    Map<String, Object> call = planner.plan("ما هي حالات المشاريع وعدد كل حالة؟", catalog()).orElseThrow();
    Map<?, ?> plan = (Map<?, ?>) call.get("plan");

    assertThat(plan.get("operation")).isEqualTo("group_count");
    assertThat(plan.get("table")).isEqualTo("projects");
    assertThat(plan.get("group_by")).isEqualTo("status");
  }

  @Test
  void plansLatestProjectsWithBoundedLimit() {
    OrbitSemanticPlanner planner = new OrbitSemanticPlanner();

    Map<String, Object> call = planner.plan("اعرض آخر 50 مشاريع", catalog()).orElseThrow();
    Map<?, ?> plan = (Map<?, ?>) call.get("plan");

    assertThat(plan.get("operation")).isEqualTo("list");
    assertThat(plan.get("limit")).isEqualTo(20);
    assertThat(((Map<?, ?>) plan.get("order_by")).get("column")).isEqualTo("created_at");
  }

  private static SemanticCatalog catalog() {
    return new SemanticCatalog("orbit", 1, "now", "hash", true, List.of(new CatalogTable(
      "projects", "projects", "project", List.of("مشروع", "مشاريع"), List.of("projects", "project"),
      List.of(
        new CatalogColumn("status", "project_status", "string", true, List.of("filter", "group"), List.of("waiting", "active"), false, true),
        new CatalogColumn("created_at", "created_at", "date", true, List.of("filter", "sort", "group"), List.of(), false, true)
      ),
      List.of("count", "list", "group_count"), true, 0
    )));
  }
}
