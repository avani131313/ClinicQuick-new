export function routeAfterLogin(r: { role: string; profile_complete?: boolean }) {
  if (r.role === "patient") return r.profile_complete === false ? "/start" : "/home";
  if (r.role === "clinician") return "/doctor";
  return "/care";
}
