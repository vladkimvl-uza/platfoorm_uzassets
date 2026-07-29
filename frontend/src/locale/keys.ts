/** Marks a fixed source-language UI key without translating it eagerly. */
export function i18nKey<const T extends string>(key: T): T {
  return key;
}
