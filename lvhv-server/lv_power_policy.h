#ifndef LV_POWER_POLICY_H
#define LV_POWER_POLICY_H

/* Default preserves the old CLI's 50 ms spacing. Not a measured inrush limit.
 * Builds may override with -DLV_POWER_ON_STAGGER_MS=<milliseconds>. */
#ifndef LV_POWER_ON_STAGGER_MS
#define LV_POWER_ON_STAGGER_MS 50
#endif
#if LV_POWER_ON_STAGGER_MS < 0
#error "LV_POWER_ON_STAGGER_MS must be nonnegative"
#endif

#endif
