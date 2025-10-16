export const getCustomerAvatar = (name: string): string => {
  const avatars = ["🙋‍♀️", "🙋‍♂️", "👩‍💼", "👨‍💼", "👩‍🎓", "👨‍🎓", "👩‍🌾", "👨‍🌾", "👩‍🍳", "👨‍🍳"];
  const index = name.charCodeAt(0) % avatars.length;
  return avatars[index];
};

export const getBusinessAvatar = (businessName: string): string => {
  const cleanName = businessName?.replace("agent-", "") || "R";
  return cleanName.charAt(0).toUpperCase();
};
