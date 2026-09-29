import type { components } from "./api";

export type { components, operations, paths } from "./api";
export * from "./events";

type S = components["schemas"];

export type Project = S["ProjectOut"];
export type ProjectCreate = S["ProjectCreate"];
export type ProjectUpdate = S["ProjectUpdate"];
export type ProjectSettings = S["ProjectSettings"];
export type Conversation = S["ConversationOut"];
export type Message = S["MessageOut"];
export type UserSettings = S["UserSettingsOut"];
export type UserSettingsUpdate = S["UserSettingsUpdate"];
export type Notification = S["NotificationOut"];
export type HealthReport = S["HealthReport"];
export type HealthCheck = S["HealthCheckResult"];
export type PermissionLevel = S["PermissionLevel"];
export type ChainVerification = S["ChainVerification"];
