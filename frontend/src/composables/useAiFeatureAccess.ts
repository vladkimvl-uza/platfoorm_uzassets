import { computed } from "vue";
import { useAiActivation } from "@/composables/useAiActivation";
import { usePermissions } from "@/composables/usePermissions";
import { useAuthStore } from "@/stores/auth";

/** Shared client-side gate for chat and embedded AI analyzers. */
export function useAiFeatureAccess() {
  const auth = useAuthStore();
  const activation = useAiActivation();
  const permissions = usePermissions("ai");

  void activation.load();

  const hasPermission = computed(() => permissions.canView.value);
  const hasAccess = computed(() => (
    hasPermission.value
    && (auth.isOwner || (activation.state.loaded && activation.state.hasAccess))
  ));
  const canUseAi = computed(() => (
    hasAccess.value
    && (activation.state.active || auth.isOwner)
  ));

  return {
    hasPermission,
    hasAccess,
    canUseAi,
    active: computed(() => activation.state.active),
  };
}
