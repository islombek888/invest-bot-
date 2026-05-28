import { Telegraf, Markup } from 'telegraf';
import { config } from './config';
import { dbService, User, Investment } from './database/db';
import http from 'http';

if (!config.botToken) {
  console.error('ERROR: BOT_TOKEN is not set in .env file!');
  process.exit(1);
}

const bot = new Telegraf(config.botToken);

// Format currency
const formatMoney = (val: number): string => {
  return val.toLocaleString('uz-UZ') + " so'm";
};

// Format date
const formatDate = (dateStr: string): string => {
  const d = new Date(dateStr);
  return `${String(d.getDate()).padStart(2, '0')}.${String(d.getMonth() + 1).padStart(2, '0')}.${d.getFullYear()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
};

// User states
interface UserState {
  state: 'NONE' | 'DEPOSIT_AMOUNT' | 'DEPOSIT_SCREENSHOT' | 'WITHDRAWAL_CARD' | 'WITHDRAWAL_AMOUNT' | 'INVEST_AMOUNT' | 'INVEST_DURATION' | 'ADMIN_CARD_CHANGE' | 'ADMIN_SET_MIN_DEP' | 'ADMIN_SET_MIN_WITHDRAW' | 'ADMIN_SET_REF_BONUS' | 'ADMIN_SET_MIN_REF' | 'ADMIN_BROADCAST' | 'ADMIN_USER_LOOKUP' | 'ADMIN_CHANGE_BALANCE_AMOUNT';
  depositAmount?: number;
  withdrawCard?: string;
  investAmount?: number;
  lookupUserId?: number;
  lookupUserAction?: 'add' | 'sub' | 'set';
}

const userStates = new Map<number, UserState>();

const getUserState = (userId: number): UserState => {
  if (!userStates.has(userId)) {
    userStates.set(userId, { state: 'NONE' });
  }
  return userStates.get(userId)!;
};

const setUserState = (userId: number, state: Partial<UserState>) => {
  const current = getUserState(userId);
  userStates.set(userId, { ...current, ...state });
};

const resetUserState = (userId: number) => {
  userStates.set(userId, { state: 'NONE' });
};

// Middleware to intercept menu buttons & commands and reset user state
bot.use((ctx, next) => {
  if (ctx.from && ctx.message && 'text' in ctx.message) {
    const text = ctx.message.text;
    const menuButtons = [
      '💳 Depozit', '💸 Pul Yechish', '📈 Investitsiya', '👥 Referal Tizimi', '👤 Kabinet',
      '❌ Bekor qilish', '📊 Statistika', '💳 Karta o\'zgartirish', '⚙️ Sozlamalar',
      '📢 Xabar yuborish', '🔍 Foydalanuvchi qidirish', '🔙 Foydalanuvchi menyusi'
    ];
    if (menuButtons.includes(text) || text.startsWith('/')) {
      resetUserState(ctx.from.id);
    }
  }
  return next();
});

// Keyboards
const getUserKeyboard = () => {
  return Markup.keyboard([
    ['💳 Depozit', '💸 Pul Yechish'],
    ['📈 Investitsiya', '👥 Referal Tizimi'],
    ['👤 Kabinet']
  ]).resize();
};

const getCancelKeyboard = () => {
  return Markup.keyboard([
    ['❌ Bekor qilish']
  ]).resize();
};

const getAdminKeyboard = () => {
  return Markup.keyboard([
    ['📊 Statistika', '💳 Karta o\'zgartirish'],
    ['⚙️ Sozlamalar', '📢 Xabar yuborish'],
    ['🔍 Foydalanuvchi qidirish'],
    ['🔙 Foydalanuvchi menyusi']
  ]).resize();
};

const getSettingsKeyboard = () => {
  return Markup.inlineKeyboard([
    [
      Markup.button.callback('💳 Min. Depozit', 'admin_conf_min_dep'),
      Markup.button.callback('💸 Min. Yechish', 'admin_conf_min_with')
    ],
    [
      Markup.button.callback('👥 Referal Bonus', 'admin_conf_ref_bonus'),
      Markup.button.callback('🏠 Admin Panel', 'admin_panel_back')
    ]
  ]);
};

// Start Command & Referral handling
bot.start((ctx) => {
  const userId = ctx.from.id;
  const username = ctx.from.username || null;
  const firstName = ctx.from.first_name || 'Foydalanuvchi';
  const startPayload = ctx.payload; // For referrals, e.g. ref_123456

  let referrerId: number | undefined;
  if (startPayload && startPayload.startsWith('ref_')) {
    const refStr = startPayload.replace('ref_', '');
    const parsedRef = parseInt(refStr, 10);
    if (!isNaN(parsedRef) && parsedRef !== userId) {
      referrerId = parsedRef;
    }
  }

  // Check if user already exists
  const existingUser = dbService.getUser(userId);

  // Create user
  dbService.createUser(userId, username, firstName, existingUser ? (existingUser.referred_by || undefined) : referrerId);

  // If new user and referred by someone, reward the referrer
  if (!existingUser && referrerId) {
    const referrer = dbService.getUser(referrerId);
    if (referrer) {
      const refBonus = parseFloat(dbService.getSetting('referral_bonus', config.referralBonus.toString()));
      dbService.updateBalance(referrerId, refBonus);

      // Notify referrer
      bot.telegram.sendMessage(
        referrerId,
        `👥 **Yangi hamkor!**\n\nSizning taklif havolangiz orqali yangi do'stingiz botga qo'shildi. Balansingizga **+${formatMoney(refBonus)}** qo'shildi!`,
        { parse_mode: 'Markdown' }
      ).catch(err => console.error('Failed to notify referrer:', err));
    }
  }

  resetUserState(userId);

  ctx.reply(
    `👋 **Assalomu alaykum, ${firstName}!**\n\n` +
    `🤖 Professional investitsiya va hamkorlik botimizga xush kelibsiz.\n\n` +
    `Bu yerda siz pulingizni investitsiya qilib, kunlik **25%** daromad olishingiz va do'stlaringizni taklif qilib pul ishlashingiz mumkin.`,
    getUserKeyboard()
  );

  // Check if admin
  if (userId === config.adminId) {
    ctx.reply('👨‍💻 Siz adminsiz. Admin panelga o\'tish uchun /admin buyrug\'ini yozing.');
  }
});

// Admin command
bot.command('admin', (ctx) => {
  if (ctx.from.id !== config.adminId) {
    return ctx.reply('❌ Kechirasiz, siz admin emassiz.');
  }

  resetUserState(ctx.from.id);
  ctx.reply('👨‍💻 **Admin paneliga xush kelibsiz!**\n\nKerakli bo\'limni tanlang:', getAdminKeyboard());
});

// Admin command: /give <userId> <amount>
bot.command('give', (ctx) => {
  if (ctx.from.id !== config.adminId) {
    return ctx.reply('❌ Kechirasiz, siz admin emassiz.');
  }

  const args = ctx.message.text.split(' ');
  if (args.length < 3) {
    return ctx.reply('⚠️ To\'g\'ri foydalanish: `/give <Telegram_ID> <miqdor>`\nMasalan: `/give 123456789 50000`', { parse_mode: 'Markdown' });
  }

  const targetId = parseInt(args[1], 10);
  const amount = parseFloat(args[2]);

  if (isNaN(targetId) || isNaN(amount) || amount <= 0) {
    return ctx.reply('❌ Xato: Iltimos to\'g\'ri ID va musbat miqdor yozing.');
  }

  const targetUser = dbService.getUser(targetId);
  if (!targetUser) {
    return ctx.reply(`❌ Foydalanuvchi topilmadi (ID: ${targetId}).`);
  }

  dbService.updateBalance(targetId, amount);
  ctx.reply(`✅ Foydalanuvchi ${targetUser.first_name} (ID: ${targetId}) balansiga **+${formatMoney(amount)}** qo'shildi.`, getAdminKeyboard());

  bot.telegram.sendMessage(
    targetId,
    `💰 Balansingiz admin tomonidan **+${formatMoney(amount)}** ga ko'paytirildi!\n` +
    `Joriy balans: **${formatMoney(targetUser.balance + amount)}**`,
    { parse_mode: 'Markdown' }
  ).catch(() => { });
});

// Admin command: /take <userId> <amount>
bot.command('take', (ctx) => {
  if (ctx.from.id !== config.adminId) {
    return ctx.reply('❌ Kechirasiz, siz admin emassiz.');
  }

  const args = ctx.message.text.split(' ');
  if (args.length < 3) {
    return ctx.reply('⚠️ To\'g\'ri foydalanish: `/take <Telegram_ID> <miqdor>`\nMasalan: `/take 123456789 50000`', { parse_mode: 'Markdown' });
  }

  const targetId = parseInt(args[1], 10);
  const amount = parseFloat(args[2]);

  if (isNaN(targetId) || isNaN(amount) || amount <= 0) {
    return ctx.reply('❌ Xato: Iltimos to\'g\'ri ID va musbat miqdor yozing.');
  }

  const targetUser = dbService.getUser(targetId);
  if (!targetUser) {
    return ctx.reply(`❌ Foydalanuvchi topilmadi (ID: ${targetId}).`);
  }

  dbService.updateBalance(targetId, -amount);
  ctx.reply(`✅ Foydalanuvchi ${targetUser.first_name} (ID: ${targetId}) balansidan **-${formatMoney(amount)}** ayirildi.`, getAdminKeyboard());

  const newBal = Math.max(0, targetUser.balance - amount);
  bot.telegram.sendMessage(
    targetId,
    `💰 Balansingizdan admin tomonidan **-${formatMoney(amount)}** ayirildi.\n` +
    `Joriy balans: **${formatMoney(newBal)}**`,
    { parse_mode: 'Markdown' }
  ).catch(() => { });
});

// Admin command: /setbal <userId> <amount>
bot.command('setbal', (ctx) => {
  if (ctx.from.id !== config.adminId) {
    return ctx.reply('❌ Kechirasiz, siz admin emassiz.');
  }

  const args = ctx.message.text.split(' ');
  if (args.length < 3) {
    return ctx.reply('⚠️ To\'g\'ri foydalanish: `/setbal <Telegram_ID> <miqdor>`\nMasalan: `/setbal 123456789 100000`', { parse_mode: 'Markdown' });
  }

  const targetId = parseInt(args[1], 10);
  const amount = parseFloat(args[2]);

  if (isNaN(targetId) || isNaN(amount) || amount < 0) {
    return ctx.reply('❌ Xato: Iltimos to\'g\'ri ID va musbat miqdor yozing.');
  }

  const targetUser = dbService.getUser(targetId);
  if (!targetUser) {
    return ctx.reply(`❌ Foydalanuvchi topilmadi (ID: ${targetId}).`);
  }

  dbService.setBalance(targetId, amount);
  ctx.reply(`✅ Foydalanuvchi ${targetUser.first_name} (ID: ${targetId}) balansi **${formatMoney(amount)}** qilib o'rnatildi.`, getAdminKeyboard());

  bot.telegram.sendMessage(
    targetId,
    `💰 Balansingiz admin tomonidan **${formatMoney(amount)}** qilib o'rnatildi!`,
    { parse_mode: 'Markdown' }
  ).catch(() => { });
});


// Cancel command handler
bot.hears('❌ Bekor qilish', (ctx) => {
  const userId = ctx.from.id;
  resetUserState(userId);
  ctx.reply('❌ Amaliyot bekor qilindi.', userId === config.adminId ? getAdminKeyboard() : getUserKeyboard());
});

// Handle Admin Navigation / Buttons
bot.hears('🔙 Foydalanuvchi menyusi', (ctx) => {
  if (ctx.from.id !== config.adminId) return;
  resetUserState(ctx.from.id);
  ctx.reply('🔙 Foydalanuvchi menyusiga qaytildi.', getUserKeyboard());
});

bot.hears('📊 Statistika', (ctx) => {
  if (ctx.from.id !== config.adminId) return;
  const stats = dbService.getStats();

  ctx.reply(
    `📊 **Bot Statistikasi:**\n\n` +
    `👥 **Jami foydalanuvchilar:** ${stats.totalUsers} ta\n` +
    `💰 **Jami tasdiqlangan depozitlar:** ${formatMoney(stats.totalDeposits)}\n` +
    `💸 **Jami tasdiqlangan to'lovlar (yechish):** ${formatMoney(stats.totalWithdrawals)}\n\n` +
    `📈 **Faol investitsiyalar soni:** ${stats.activeInvestmentsCount} ta\n` +
    `💰 **Faol investitsiyalar hajmi:** ${formatMoney(stats.activeInvestmentsSum)}`
  );
});

bot.hears('💳 Karta o\'zgartirish', (ctx) => {
  if (ctx.from.id !== config.adminId) return;

  const currentCard = dbService.getSetting('card_details', config.cardDetails);
  setUserState(ctx.from.id, { state: 'ADMIN_CARD_CHANGE' });

  ctx.reply(
    `💳 **Karta raqamini o'zgartirish:**\n\n` +
    `Joriy karta ma'lumotlari:\n` +
    `\`${currentCard}\`\n\n` +
    `Yangi karta ma'lumotlarini kiriting (karta raqami va egasining ismi):`,
    getCancelKeyboard()
  );
});

bot.hears('⚙️ Sozlamalar', (ctx) => {
  if (ctx.from.id !== config.adminId) return;

  const minDep = parseFloat(dbService.getSetting('min_deposit', config.minDeposit.toString()));
  const minWith = parseFloat(dbService.getSetting('min_withdrawal', config.minWithdrawal.toString()));
  const refBonus = parseFloat(dbService.getSetting('referral_bonus', config.referralBonus.toString()));

  ctx.reply(
    `⚙️ **Tizim Sozlamalari:**\n\n` +
    `💳 **Minimal depozit:** ${formatMoney(minDep)}\n` +
    `💸 **Minimal yechish:** ${formatMoney(minWith)}\n` +
    `👥 **Referal bonus:** ${formatMoney(refBonus)}\n\n` +
    `O'zgartirmoqchi bo'lgan sozlamani tanlang:`,
    getSettingsKeyboard()
  );
});

bot.hears('📢 Xabar yuborish', (ctx) => {
  if (ctx.from.id !== config.adminId) return;

  setUserState(ctx.from.id, { state: 'ADMIN_BROADCAST' });
  ctx.reply(
    `📢 **Foydalanuvchilarga xabar yuborish:**\n\n` +
    `Foydalanuvchilarga yubormoqchi bo'lgan xabaringizni yozing (rasm, matn, havola hammasi bo'lishi mumkin):`,
    getCancelKeyboard()
  );
});

bot.hears('🔍 Foydalanuvchi qidirish', (ctx) => {
  if (ctx.from.id !== config.adminId) return;

  setUserState(ctx.from.id, { state: 'ADMIN_USER_LOOKUP' });
  ctx.reply(
    `🔍 **Foydalanuvchini qidirish:**\n\n` +
    `Foydalanuvchining Telegram ID yoki username (boshida @ belgisiz) kiriting:`,
    getCancelKeyboard()
  );
});

// Inline callback for Settings
bot.action('admin_conf_min_dep', (ctx) => {
  if (ctx.from.id !== config.adminId) return;
  setUserState(ctx.from.id, { state: 'ADMIN_SET_MIN_DEP' });
  ctx.answerCbQuery();
  ctx.reply(`💳 **Minimal depozit miqdorini o'zgartirish:**\n\nYangi miqdorni yozing (masalan: 15000):`, getCancelKeyboard());
});

bot.action('admin_conf_min_with', (ctx) => {
  if (ctx.from.id !== config.adminId) return;
  setUserState(ctx.from.id, { state: 'ADMIN_SET_MIN_WITHDRAW' });
  ctx.answerCbQuery();
  ctx.reply(`💸 **Minimal yechish miqdorini o'zgartirish:**\n\nYangi miqdorni yozing (masalan: 20000):`, getCancelKeyboard());
});

bot.action('admin_conf_ref_bonus', (ctx) => {
  if (ctx.from.id !== config.adminId) return;
  setUserState(ctx.from.id, { state: 'ADMIN_SET_REF_BONUS' });
  ctx.answerCbQuery();
  ctx.reply(`👥 **Referal bonus miqdorini o'zgartirish:**\n\nYangi bonus miqdorini yozing (masalan: 2000):`, getCancelKeyboard());
});

bot.action('admin_conf_min_ref', (ctx) => {
  if (ctx.from.id !== config.adminId) return;
  setUserState(ctx.from.id, { state: 'ADMIN_SET_MIN_REF' });
  ctx.answerCbQuery();
  ctx.reply(`👥 **Min. referal sonini o'zgartirish:**\n\nPul yechish uchun foydalanuvchi taklif qilishi kerak bo'lgan eng kam do'stlar sonini kiriting (masalan: 3):`, getCancelKeyboard());
});

bot.action('admin_panel_back', (ctx) => {
  if (ctx.from.id !== config.adminId) return;
  ctx.answerCbQuery();
  resetUserState(ctx.from.id);
  ctx.reply('👨‍💻 Admin panel bosh sahifasi:', getAdminKeyboard());
});

// Handle User Actions / Buttons
bot.hears('👤 Kabinet', (ctx) => {
  const userId = ctx.from.id;
  let user = dbService.getUser(userId);
  if (!user) {
    user = dbService.createUser(userId, ctx.from.username || null, ctx.from.first_name);
  }

  const refCount = dbService.getReferralCount(userId);
  const activeInvs = dbService.getUserInvestments(userId).filter(i => i.status === 'active');

  ctx.reply(
    `👤 **Sizning Kabinetingiz:**\n\n` +
    `🆔 **ID:** \`${user.id}\`\n` +
    `👤 **Ism:** ${user.first_name}\n` +
    `💰 **Balans:** **${formatMoney(user.balance)}**\n\n` +
    `👥 **Siz taklif qilgan hamkorlar:** **${refCount} ta**\n` +
    `📈 **Faol investitsiyalaringiz:** **${activeInvs.length} ta**`,
    { parse_mode: 'Markdown', ...getUserKeyboard() }
  );
});

bot.hears('👥 Referal Tizimi', (ctx) => {
  const userId = ctx.from.id;
  const refCount = dbService.getReferralCount(userId);
  const refBonus = parseFloat(dbService.getSetting('referral_bonus', config.referralBonus.toString()));

  // Create referral link
  const botUsername = ctx.botInfo.username;
  const refLink = `https://t.me/${botUsername}?start=ref_${userId}`;

  ctx.reply(
    `👥 **Hamkorlik (Referal) Dasturi:**\n\n` +
    `Do'stlaringizni botga taklif qiling va har bir muvaffaqiyatli ro'yxatdan o'tgan do'stingiz uchun **${formatMoney(refBonus)}** bonus oling!\n\n` +
    `🔗 **Sizning taklif havolangiz:**\n\`${refLink}\`\n\n` +
    `📊 **Statistika:**\n` +
    `Taklif qilingan do'stlar: **${refCount} ta**\n` +
    `Ishlab topilgan jami mukofot: **${formatMoney(refCount * refBonus)}**`,
    { parse_mode: 'Markdown', ...getUserKeyboard() }
  );
});

bot.hears('💳 Depozit', (ctx) => {
  const userId = ctx.from.id;
  const currentCard = dbService.getSetting('card_details', config.cardDetails);
  const minDep = parseFloat(dbService.getSetting('min_deposit', config.minDeposit.toString()));

  setUserState(userId, { state: 'DEPOSIT_AMOUNT' });

  ctx.reply(
    `💳 **Balansni to'ldirish (Depozit):**\n\n` +
    `Siz bizning rasmiy kartamizga pul o'tkazishingiz kerak:\n` +
    `➡️ Karta: \`${currentCard}\`\n\n` +
    `⚠️ Minimal depozit miqdori: **${formatMoney(minDep)}**\n\n` +
    `O'tkazma tugagach, to'lovni tasdiqlash uchun botga yuborishingiz kerak.\n\n` +
    `💰 **Qancha pul o'tkazdingiz?** (Faqat raqamlar bilan yozing, masalan: 50000):`,
    { parse_mode: 'Markdown', ...getCancelKeyboard() }
  );
});

bot.hears('💸 Pul Yechish', (ctx) => {
  const userId = ctx.from.id;
  const user = dbService.getUser(userId);
  if (!user) return;

  const minWith = parseFloat(dbService.getSetting('min_withdrawal', config.minWithdrawal.toString()));

  if (user.balance < minWith) {
    return ctx.reply(
      `❌ **Balansingiz yetarli emas!**\n\n` +
      `Minimal yechib olish miqdori: **${formatMoney(minWith)}**\n` +
      `Sizning balansingiz: **${formatMoney(user.balance)}**`
    );
  }

  setUserState(userId, { state: 'WITHDRAWAL_CARD' });
  ctx.reply(
    `💸 **Pul yechish (Kassa):**\n\n` +
    `Sizning balansingiz: **${formatMoney(user.balance)}**\n` +
    `Minimal yechish: **${formatMoney(minWith)}**\n\n` +
    `💳 **Pul o'tkaziladigan karta raqamini kiriting:**\n(Karta raqamini va agar kerak bo'lsa egasining ismini ham yozishingiz mumkin, masalan: 8600123456789012 - Ali Valiyev):`,
    getCancelKeyboard()
  );
});

bot.hears('📈 Investitsiya', (ctx) => {
  const userId = ctx.from.id;
  const user = dbService.getUser(userId);
  if (!user) return;

  const userInvs = dbService.getUserInvestments(userId);
  const activeInvs = userInvs.filter(i => i.status === 'active');
  const minDep = parseFloat(dbService.getSetting('min_deposit', config.minDeposit.toString()));

  let msg = `📈 **Investitsiya bo'limi**\n\n` +
    `Sarmoya kiriting va pulingizni har kuni **25%** ga ko'paytiring!\n` +
    `⏳ Minimal investitsiya muddati: **7 kun**.\n` +
    `Foyda har kuni hisoblab boriladi va muddat yakunida sarmoyangiz bilan birga balansingizga qo'shiladi.\n\n` +
    `📊 **Misol uchun:**\n` +
    `- 100,000 so'm investitsiya qilsangiz:\n` +
    `  Kuniga: 25,000 so'mdan foyda\n` +
    `  7 kunda jami foyda: 175,000 so'm\n` +
    `  💰 Yakunda balansingizga qo'shiladi: **275,000 so'm**\n\n` +
    `💵 Sizning balansingiz: **${formatMoney(user.balance)}**\n` +
    `⚠️ Minimal investitsiya miqdori: **${formatMoney(minDep)}**\n\n`;

  if (activeInvs.length > 0) {
    msg += `💼 **Sizning faol investitsiyalaringiz:**\n`;
    activeInvs.forEach((inv, index) => {
      const start = new Date(inv.start_date).getTime();
      const now = new Date().getTime();
      const elapsedDays = Math.floor((now - start) / (24 * 60 * 60 * 1000));
      const actualElapsed = Math.min(elapsedDays, inv.duration_days);
      const currentProfit = inv.amount * 0.25 * actualElapsed;
      const expectedTotal = inv.amount * (1 + 0.25 * inv.duration_days);

      msg += `\n${index + 1}. **ID: #INV_${inv.id}**\n` +
        `   Sarmoya: ${formatMoney(inv.amount)}\n` +
        `   Kunlar: ${actualElapsed}/${inv.duration_days} kun o'tdi\n` +
        `   Joriy foyda: +${formatMoney(currentProfit)}\n` +
        `   Kutilayotgan umumiy: ${formatMoney(expectedTotal)}\n` +
        `   Tugash vaqti: ${formatDate(inv.end_date)}\n`;
    });
    msg += `\n`;
  }

  setUserState(userId, { state: 'INVEST_AMOUNT' });
  ctx.reply(
    msg + `💰 **Investitsiya qilmoqchi bo'lgan miqdoringizni yozing:**\n(Faqat raqamlar bilan, masalan: 100000):`,
    { parse_mode: 'Markdown', ...getCancelKeyboard() }
  );
});

// Inline actions for Admin User Lookup
bot.action(/^admin_bal_(add|sub|set)_(\d+)$/, (ctx) => {
  if (ctx.from.id !== config.adminId) return;

  const action = ctx.match[1] as 'add' | 'sub' | 'set';
  const targetId = parseInt(ctx.match[2], 10);

  const user = dbService.getUser(targetId);
  if (!user) {
    return ctx.reply('❌ Foydalanuvchi topilmadi.');
  }

  setUserState(ctx.from.id, {
    state: 'ADMIN_CHANGE_BALANCE_AMOUNT',
    lookupUserId: targetId,
    lookupUserAction: action
  });

  let actionText = '';
  if (action === 'add') actionText = "qo'shmoqchi bo'lgan";
  if (action === 'sub') actionText = "ayirmoqchi bo'lgan";
  if (action === 'set') actionText = "o'rnatmoqchi bo'lgan yangi";

  ctx.answerCbQuery();
  ctx.reply(
    `💰 Foydalanuvchi: ${user.first_name} (${user.id})\n` +
    `Joriy balans: ${formatMoney(user.balance)}\n\n` +
    `Foydalanuvchi balansiga ${actionText} miqdorni yozing:`,
    getCancelKeyboard()
  );
});

// Approve/Reject Inline Actions for Deposits
bot.action(/^deposit_app_(\d+)$/, async (ctx) => {
  if (ctx.from.id !== config.adminId) return;

  const depositId = parseInt(ctx.match[1], 10);
  const deposit = dbService.getDeposit(depositId);

  if (!deposit) {
    return ctx.reply('❌ Depozit so\'rovi topilmadi.');
  }

  if (deposit.status !== 'pending') {
    return ctx.reply(`❌ Bu so'rov allaqachon qayta ishlangan. Holat: ${deposit.status}`);
  }

  // Approve
  dbService.updateDepositStatus(depositId, 'approved');
  dbService.updateBalance(deposit.user_id, deposit.amount);

  ctx.answerCbQuery('Depozit tasdiqlandi');

  // Edit admin message
  try {
    await ctx.editMessageCaption(
      `✅ **Depozit Tasdiqlandi (ID: #${depositId})**\n\n` +
      `👤 Foydalanuvchi: ${deposit.user_id} ga **${formatMoney(deposit.amount)}** qo'shildi.`,
      { reply_markup: undefined }
    );
  } catch (e) {
    ctx.reply(`✅ Depozit #${depositId} tasdiqlandi.`);
  }

  // Notify User
  bot.telegram.sendMessage(
    deposit.user_id,
    `🎉 **Depozitingiz tasdiqlandi!**\n\n` +
    `Balansingizga **+${formatMoney(deposit.amount)}** muvaffaqiyatli qo'shildi.\n` +
    `Hozirda bemalol investitsiya qilishingiz mumkin!`,
    { parse_mode: 'Markdown', ...getUserKeyboard() }
  ).catch(err => console.error('Failed to notify user about deposit approval:', err));
});

bot.action(/^deposit_rej_(\d+)$/, async (ctx) => {
  if (ctx.from.id !== config.adminId) return;

  const depositId = parseInt(ctx.match[1], 10);
  const deposit = dbService.getDeposit(depositId);

  if (!deposit) {
    return ctx.reply('❌ Depozit so\'rovi topilmadi.');
  }

  if (deposit.status !== 'pending') {
    return ctx.reply(`❌ Bu so'rov allaqachon qayta ishlangan. Holat: ${deposit.status}`);
  }

  // Reject
  dbService.updateDepositStatus(depositId, 'rejected');

  ctx.answerCbQuery('Depozit rad etildi');

  // Edit admin message
  try {
    await ctx.editMessageCaption(
      `❌ **Depozit Rad Etildi (ID: #${depositId})**\n\n` +
      `Foydalanuvchi: ${deposit.user_id}\n` +
      `Miqdor: ${formatMoney(deposit.amount)}`,
      { reply_markup: undefined }
    );
  } catch (e) {
    ctx.reply(`❌ Depozit #${depositId} rad etildi.`);
  }

  // Notify User
  bot.telegram.sendMessage(
    deposit.user_id,
    `❌ **Depozitingiz rad etildi!**\n\n` +
    `Siz yuborgan **${formatMoney(deposit.amount)}** lik to'lov skrinshoti tasdiqlanmadi.\n` +
    `Muammo yuzasidan adminga murojaat qiling.`,
    { parse_mode: 'Markdown', ...getUserKeyboard() }
  ).catch(err => console.error('Failed to notify user about deposit rejection:', err));
});

// Approve/Reject Inline Actions for Withdrawals
bot.action(/^withdraw_app_(\d+)$/, async (ctx) => {
  if (ctx.from.id !== config.adminId) return;

  const withdrawalId = parseInt(ctx.match[1], 10);
  const withdrawal = dbService.getWithdrawal(withdrawalId);

  if (!withdrawal) {
    return ctx.reply('❌ Pul yechish so\'rovi topilmadi.');
  }

  if (withdrawal.status !== 'pending') {
    return ctx.reply(`❌ Bu so'rov allaqachon qayta ishlangan. Holat: ${withdrawal.status}`);
  }

  // Approve
  dbService.updateWithdrawalStatus(withdrawalId, 'approved');

  ctx.answerCbQuery('Pul yechish tasdiqlandi');

  // Edit admin message
  try {
    await ctx.editMessageText(
      `✅ **Pul Yechish Tasdiqlandi (ID: #${withdrawalId})**\n\n` +
      `Foydalanuvchi: ${withdrawal.user_id}\n` +
      `Karta: \`${withdrawal.card_number}\`\n` +
      `Miqdor: **${formatMoney(withdrawal.amount)}** o'tkazib berildi.`,
      { parse_mode: 'Markdown', reply_markup: undefined }
    );
  } catch (e) {
    ctx.reply(`✅ Pul yechish #${withdrawalId} tasdiqlandi.`);
  }

  // Notify User
  bot.telegram.sendMessage(
    withdrawal.user_id,
    `🎉 **Pul yechish so'rovingiz tasdiqlandi!**\n\n` +
    `Karta: \`${withdrawal.card_number}\`\n` +
    `Miqdor: **${formatMoney(withdrawal.amount)}** o'tkazib berildi.\n` +
    `Hisobingizni tekshirib ko'ring!`,
    { parse_mode: 'Markdown', ...getUserKeyboard() }
  ).catch(err => console.error('Failed to notify user about withdrawal approval:', err));
});

bot.action(/^withdraw_rej_(\d+)$/, async (ctx) => {
  if (ctx.from.id !== config.adminId) return;

  const withdrawalId = parseInt(ctx.match[1], 10);
  const withdrawal = dbService.getWithdrawal(withdrawalId);

  if (!withdrawal) {
    return ctx.reply('❌ Pul yechish so\'rovi topilmadi.');
  }

  if (withdrawal.status !== 'pending') {
    return ctx.reply(`❌ Bu so'rov allaqachon qayta ishlangan. Holat: ${withdrawal.status}`);
  }

  // Reject & Refund to User
  dbService.updateWithdrawalStatus(withdrawalId, 'rejected');
  dbService.updateBalance(withdrawal.user_id, withdrawal.amount);

  ctx.answerCbQuery('Pul yechish rad etildi, pul qaytarildi');

  // Edit admin message
  try {
    await ctx.editMessageText(
      `❌ **Pul Yechish Rad Etildi (ID: #${withdrawalId})**\n\n` +
      `Foydalanuvchi: ${withdrawal.user_id}\n` +
      `Karta: \`${withdrawal.card_number}\`\n` +
      `Miqdor: **${formatMoney(withdrawal.amount)}** qaytarildi.`,
      { parse_mode: 'Markdown', reply_markup: undefined }
    );
  } catch (e) {
    ctx.reply(`❌ Pul yechish #${withdrawalId} rad etildi, mablag' qaytarildi.`);
  }

  // Notify User
  bot.telegram.sendMessage(
    withdrawal.user_id,
    `❌ **Pul yechish so'rovingiz rad etildi!**\n\n` +
    `Miqdor: **${formatMoney(withdrawal.amount)}** balansingizga qaytarildi.\n` +
    `Muammo bo'lsa adminga murojaat qiling.`,
    { parse_mode: 'Markdown', ...getUserKeyboard() }
  ).catch(err => console.error('Failed to notify user about withdrawal rejection:', err));
});

// Generic message handler to handle inputs based on states
bot.on('message', async (ctx) => {
  const userId = ctx.from.id;
  const userState = getUserState(userId);

  // Handle Admin Broadcast
  if (userState.state === 'ADMIN_BROADCAST') {
    if (ctx.from.id !== config.adminId) return;

    resetUserState(userId);
    ctx.reply('⏳ Xabar barcha foydalanuvchilarga yuborilmoqda. Iltimos kuting...');

    const userIds = dbService.getAllUserIds();

    let success = 0;
    let failed = 0;

    for (const targetUserId of userIds) {
      try {
        await ctx.copyMessage(targetUserId);
        success++;
      } catch (e) {
        failed++;
      }
    }

    ctx.reply(
      `📢 **Xabar tarqatish yakunlandi!**\n\n` +
      `✅ Muvaffaqiyatli: ${success} ta\n` +
      `❌ Muvaffaqiyatsiz: ${failed} ta`,
      getAdminKeyboard()
    );
    return;
  }

  // Handle text-based states
  const text = ('text' in ctx.message) ? ctx.message.text : '';

  // Handle deposit amount input
  if (userState.state === 'DEPOSIT_AMOUNT') {
    const amount = parseFloat(text);
    const minDep = parseFloat(dbService.getSetting('min_deposit', config.minDeposit.toString()));

    if (isNaN(amount) || amount <= 0) {
      return ctx.reply('❌ Iltimos, musbat raqam kiriting (masalan: 50000):');
    }

    if (amount < minDep) {
      return ctx.reply(`❌ Minimal depozit miqdori: **${formatMoney(minDep)}**.\nIltimos, qayta kiriting:`, { parse_mode: 'Markdown' });
    }

    setUserState(userId, { state: 'DEPOSIT_SCREENSHOT', depositAmount: amount });
    ctx.reply(
      `💸 Katta rahmat!\n` +
      `Miqdor: **${formatMoney(amount)}**\n\n` +
      `Endi ushbu to'lovni tasdiqlovchi **skrinshot (check rasm ko'rinishida)** ni botga yuboring:`,
      { parse_mode: 'Markdown', ...getCancelKeyboard() }
    );
    return;
  }

  // Handle deposit screenshot input (if they sent text instead of photo)
  if (userState.state === 'DEPOSIT_SCREENSHOT' && !('photo' in ctx.message)) {
    return ctx.reply('❌ Iltimos, faqat rasm (screenshot) shaklida to\'lov chekini yuboring. Amaldagi chekni bekor qilish uchun pastdagi tugmani bosing:');
  }

  // Handle deposit screenshot photo upload
  if (userState.state === 'DEPOSIT_SCREENSHOT' && 'photo' in ctx.message) {
    const photos = ctx.message.photo;
    const photoFileId = photos[photos.length - 1].file_id;
    const amount = userState.depositAmount!;

    // Save to Database
    const deposit = dbService.createDeposit(userId, amount, photoFileId);

    // Reset state
    resetUserState(userId);

    ctx.reply(
      `✅ **To'lov ma'lumotlari adminga tasdiqlash uchun yuborildi.**\n` +
      `Iltimos biroz kuting, admin tomonidan tekshirilib tasdiqlangach pul hisobingizga tushadi.`,
      { parse_mode: 'Markdown', ...getUserKeyboard() }
    );

    // Notify Admin
    bot.telegram.sendPhoto(
      config.adminId,
      photoFileId,
      {
        caption: `📥 **Yangi Depozit So'rovi (ID: #${deposit.id})**\n\n` +
          `👤 Foydalanuvchi: ${ctx.from.first_name} ${ctx.from.username ? `(@${ctx.from.username})` : ''}\n` +
          `🆔 Telegram ID: \`${userId}\`\n` +
          `💰 Miqdor: **${formatMoney(amount)}**\n\n` +
          `Iltimos, depozit to'lovini tekshirib tasdiqlang:`,
        parse_mode: 'Markdown',
        reply_markup: Markup.inlineKeyboard([
          [
            Markup.button.callback('✅ Tasdiqlash', `deposit_app_${deposit.id}`),
            Markup.button.callback('❌ Rad etish', `deposit_rej_${deposit.id}`)
          ]
        ]).reply_markup
      }
    ).catch(err => console.error('Failed to notify admin about new deposit:', err));
    return;
  }

  // Handle withdrawal card input
  if (userState.state === 'WITHDRAWAL_CARD') {
    if (!text || text.trim().length < 8) {
      return ctx.reply('❌ Iltimos, to\'g\'ri karta ma\'lumotlarini kiriting (masalan: 8600123456789012):');
    }

    setUserState(userId, { state: 'WITHDRAWAL_AMOUNT', withdrawCard: text });

    const user = dbService.getUser(userId)!;
    ctx.reply(
      `💳 Karta: \`${text}\`\n\n` +
      `Endi balansingizdan yechmoqchi bo'lgan miqdorni kiriting (faqat raqamlar bilan):\n` +
      `Sizning balansingiz: **${formatMoney(user.balance)}**`,
      { parse_mode: 'Markdown', ...getCancelKeyboard() }
    );
    return;
  }

  // Handle withdrawal amount input
  if (userState.state === 'WITHDRAWAL_AMOUNT') {
    const amount = parseFloat(text);
    const user = dbService.getUser(userId)!;
    const minWith = parseFloat(dbService.getSetting('min_withdrawal', config.minWithdrawal.toString()));

    if (isNaN(amount) || amount <= 0) {
      return ctx.reply('❌ Iltimos, musbat son yozing (masalan: 50000):');
    }

    if (amount < minWith) {
      return ctx.reply(`❌ Minimal yechish miqdori: **${formatMoney(minWith)}**.\nQayta kiriting:`);
    }

    if (amount > user.balance) {
      return ctx.reply(`❌ Balansingizda mablag' yetarli emas!\nBalansingiz: **${formatMoney(user.balance)}**\nQayta kiriting:`);
    }

    // Deduct balance immediately
    dbService.updateBalance(userId, -amount);

    // Save to Database
    const withdrawal = dbService.createWithdrawal(userId, amount, userState.withdrawCard!);

    // Reset state
    resetUserState(userId);

    ctx.reply(
      `✅ **Pul yechish so'rovingiz adminga yuborildi.**\n` +
      `Biroz kuting, admin tomonidan to'lov amalga oshirilgach sizga xabar beriladi.`,
      getUserKeyboard()
    );

    // Notify Admin
    bot.telegram.sendMessage(
      config.adminId,
      `📤 **Yangi Pul Yechish So'rovi (ID: #${withdrawal.id})**\n\n` +
      `👤 Foydalanuvchi: ${ctx.from.first_name} ${ctx.from.username ? `(@${ctx.from.username})` : ''}\n` +
      `🆔 Telegram ID: \`${userId}\`\n` +
      `💳 Karta: \`${userState.withdrawCard}\`\n` +
      `💰 Yechish miqdori: **${formatMoney(amount)}**\n\n` +
      `To'lovni amalga oshirgach quyidagi tugmalarni bosing:`,
      {
        parse_mode: 'Markdown',
        ...Markup.inlineKeyboard([

          [
            Markup.button.callback('✅ To\'lov qilindi (Tasdiqlash)', `withdraw_app_${withdrawal.id}`),
            Markup.button.callback('❌ Rad etish (Pulni qaytarish)', `withdraw_rej_${withdrawal.id}`)
          ]
        ])
      }
    ).catch(err => console.error('Failed to notify admin about new withdrawal:', err));
    return;
  }

  // Handle investment amount input
  if (userState.state === 'INVEST_AMOUNT') {
    const amount = parseFloat(text);
    const user = dbService.getUser(userId)!;
    const minDep = parseFloat(dbService.getSetting('min_deposit', config.minDeposit.toString()));

    if (isNaN(amount) || amount <= 0) {
      return ctx.reply('❌ Iltimos, musbat raqam kiriting (masalan: 100000):');
    }

    if (amount < minDep) {
      return ctx.reply(`❌ Minimal investitsiya miqdori: **${formatMoney(minDep)}**.\nQayta kiriting:`);
    }

    if (amount > user.balance) {
      return ctx.reply(`❌ Balansingizda sarmoya kiritish uchun yetarli mablag' yo'q!\nBalansingiz: **${formatMoney(user.balance)}**\nIltimos, avval depozit qiling yoki kamroq miqdor kiriting:`);
    }

    setUserState(userId, { state: 'INVEST_DURATION', investAmount: amount });
    ctx.reply(
      `💰 Sarmoya miqdori: **${formatMoney(amount)}**\n\n` +
      `Necha kunga investitsiya kiritmoqchisiz?\n` +
      `📅 **Eng kam muddat: 7 kun**\n` +
      `Kunlik daromad: **25%**\n\n` +
      `Iltimos, kunlar sonini yozing (faqat raqamlar, masalan: 7):`,
      { parse_mode: 'Markdown', ...getCancelKeyboard() }
    );
    return;
  }

  // Handle investment duration input
  if (userState.state === 'INVEST_DURATION') {
    const days = parseInt(text, 10);

    if (isNaN(days) || days < 7) {
      return ctx.reply('❌ Eng kam investitsiya muddati 7 kun bo\'lishi kerak. Iltimos, 7 yoki undan katta son kiriting:');
    }

    const amount = userState.investAmount!;
    const user = dbService.getUser(userId)!;

    // Double check balance just in case
    if (amount > user.balance) {
      resetUserState(userId);
      return ctx.reply('❌ Xatolik: Balansingizda yetarli mablag\' qolmadi.', getUserKeyboard());
    }

    // Deduct balance
    dbService.updateBalance(userId, -amount);

    // Create investment
    const inv = dbService.createInvestment(userId, amount, days);

    // Reset state
    resetUserState(userId);

    const dailyProfit = amount * 0.25;
    const totalProfit = dailyProfit * days;
    const expectedPayout = amount + totalProfit;

    ctx.reply(
      `✅ **Investitsiya muvaffaqiyatli boshlandi!**\n\n` +
      `📈 Investitsiya ID: \`#INV_${inv.id}\`\n` +
      `💰 Kiritilgan sarmoya: **${formatMoney(amount)}**\n` +
      `📅 Muddat: **${days} kun**\n` +
      `🔥 Kunlik foyda: **25% (+${formatMoney(dailyProfit)})**\n` +
      `💸 Kutilayotgan jami foyda: **+${formatMoney(totalProfit)}**\n` +
      `💰 Yakuniy umumiy to'lov: **${formatMoney(expectedPayout)}**\n` +
      `⏳ Tugash sanasi: **${formatDate(inv.end_date)}**\n\n` +
      `Muddati tugagach, barcha pul va daromad avtomatik ravishda balansingizga qaytadi!`,
      { parse_mode: 'Markdown', ...getUserKeyboard() }
    );
    return;
  }

  // Handle Admin Card Change
  if (userState.state === 'ADMIN_CARD_CHANGE') {
    if (ctx.from.id !== config.adminId) return;

    if (!text || text.trim().length === 0) {
      return ctx.reply('❌ Karta ma\'lumotlari bo\'sh bo\'lishi mumkin emas. Iltimos yozing:');
    }

    dbService.setSetting('card_details', text);
    resetUserState(ctx.from.id);

    ctx.reply(`✅ **Karta ma'lumotlari yangilandi!**\n\nYangi karta:\n\`${text}\``, { parse_mode: 'Markdown', ...getAdminKeyboard() });
    return;
  }

  // Handle Admin setting changes
  if (userState.state === 'ADMIN_SET_MIN_DEP') {
    if (ctx.from.id !== config.adminId) return;
    const val = parseFloat(text);
    if (isNaN(val) || val <= 0) {
      return ctx.reply('❌ Iltimos, musbat raqam kiriting:');
    }
    dbService.setSetting('min_deposit', val.toString());
    resetUserState(ctx.from.id);
    ctx.reply(`✅ **Minimal depozit miqdori o'rnatildi:** ${formatMoney(val)}`, getAdminKeyboard());
    return;
  }

  if (userState.state === 'ADMIN_SET_MIN_WITHDRAW') {
    if (ctx.from.id !== config.adminId) return;
    const val = parseFloat(text);
    if (isNaN(val) || val <= 0) {
      return ctx.reply('❌ Iltimos, musbat raqam kiriting:');
    }
    dbService.setSetting('min_withdrawal', val.toString());
    resetUserState(ctx.from.id);
    ctx.reply(`✅ **Minimal yechish miqdori o'rnatildi:** ${formatMoney(val)}`, getAdminKeyboard());
    return;
  }

  if (userState.state === 'ADMIN_SET_REF_BONUS') {
    if (ctx.from.id !== config.adminId) return;
    const val = parseFloat(text);
    if (isNaN(val) || val <= 0) {
      return ctx.reply('❌ Iltimos, musbat raqam kiriting:');
    }
    dbService.setSetting('referral_bonus', val.toString());
    resetUserState(ctx.from.id);
    ctx.reply(`✅ **Referal bonus miqdori o'rnatildi:** ${formatMoney(val)}`, getAdminKeyboard());
    return;
  }

  if (userState.state === 'ADMIN_SET_MIN_REF') {
    if (ctx.from.id !== config.adminId) return;
    const val = parseInt(text, 10);
    if (isNaN(val) || val < 0) {
      return ctx.reply('❌ Iltimos, musbat raqam yoki 0 kiriting:');
    }
    dbService.setSetting('min_referrals', val.toString());
    resetUserState(ctx.from.id);
    ctx.reply(`✅ **Minimal referal soni o'rnatildi:** ${val} ta`, getAdminKeyboard());
    return;
  }

  // Handle Admin User Lookup
  if (userState.state === 'ADMIN_USER_LOOKUP') {
    if (ctx.from.id !== config.adminId) return;

    let targetUser: User | null = null;
    const parsedId = parseInt(text, 10);

    if (!isNaN(parsedId)) {
      targetUser = dbService.getUser(parsedId);
    } else {
      targetUser = dbService.getUserByUsername(text);
    }

    if (!targetUser) {
      return ctx.reply('❌ Bunday foydalanuvchi topilmadi. Qayta kiriting (ID yoki username):');
    }

    resetUserState(ctx.from.id);
    const refCount = dbService.getReferralCount(targetUser.id);

    ctx.reply(
      `🔍 **Foydalanuvchi ma'lumotlari:**\n\n` +
      `👤 Ism: ${targetUser.first_name}\n` +
      `🆔 ID: \`${targetUser.id}\`\n` +
      `👤 Username: ${targetUser.username ? `@${targetUser.username}` : "yo'q"}\n` +
      `💰 Balans: **${formatMoney(targetUser.balance)}**\n` +
      `👥 Taklif etilgan do'stlar: **${refCount} ta**\n` +
      `📅 Ro'yxatdan o'tgan: ${formatDate(targetUser.created_at)}\n\n` +
      `Balansni o'zgartirish:`,
      {
        parse_mode: 'Markdown',
        ...Markup.inlineKeyboard([
          [
            Markup.button.callback("➕ Balans qo'shish", `admin_bal_add_${targetUser.id}`),
            Markup.button.callback("➖ Balans ayirish", `admin_bal_sub_${targetUser.id}`)
          ],
          [
            Markup.button.callback("✏️ Balans o'rnatish", `admin_bal_set_${targetUser.id}`),
            Markup.button.callback("🏠 Admin Panel", `admin_panel_back`)
          ]
        ])
      }
    );
    return;
  }

  // Handle Admin Change Balance Amount
  if (userState.state === 'ADMIN_CHANGE_BALANCE_AMOUNT') {
    if (ctx.from.id !== config.adminId) return;
    const amount = parseFloat(text);

    if (isNaN(amount) || amount < 0) {
      return ctx.reply('❌ Iltimos, musbat raqam kiriting:');
    }

    const targetId = userState.lookupUserId!;
    const action = userState.lookupUserAction!;

    const targetUser = dbService.getUser(targetId);
    if (!targetUser) {
      resetUserState(ctx.from.id);
      return ctx.reply('❌ Foydalanuvchi topilmadi.', getAdminKeyboard());
    }

    if (action === 'add') {
      dbService.updateBalance(targetId, amount);
      ctx.reply(`✅ ${targetUser.first_name} balansiga **+${formatMoney(amount)}** qo'shildi.`, getAdminKeyboard());
      bot.telegram.sendMessage(targetId, `💰 Balansingizga admin tomonidan **+${formatMoney(amount)}** qo'shildi!`).catch(() => { });
    } else if (action === 'sub') {
      dbService.updateBalance(targetId, -amount);
      ctx.reply(`✅ ${targetUser.first_name} balansidan **-${formatMoney(amount)}** ayirildi.`, getAdminKeyboard());
      bot.telegram.sendMessage(targetId, `💰 Balansingizdan admin tomonidan **-${formatMoney(amount)}** ayirildi.`).catch(() => { });
    } else if (action === 'set') {
      dbService.setBalance(targetId, amount);
      ctx.reply(`✅ ${targetUser.first_name} balansi **${formatMoney(amount)}** deb belgilandi.`, getAdminKeyboard());
      bot.telegram.sendMessage(targetId, `💰 Balansingiz admin tomonidan **${formatMoney(amount)}** qilib o'rnatildi!`).catch(() => { });
    }

    resetUserState(ctx.from.id);
    return;
  }
});

// Scheduler for investment checking
async function checkCompletedInvestments() {
  try {
    const active = dbService.getActiveInvestments();
    const now = new Date();
    for (const inv of active) {
      const endDate = new Date(inv.end_date);
      if (now >= endDate) {
        dbService.completeInvestment(inv.id);
        const dailyProfit = inv.amount * 0.25;
        const totalProfit = dailyProfit * inv.duration_days;
        const payout = inv.amount + totalProfit;

        dbService.updateBalance(inv.user_id, payout);

        // Notify user
        try {
          await bot.telegram.sendMessage(
            inv.user_id,
            `🎉 **Investitsiya muddati yakunlandi!**\n\n` +
            `📈 ID: \`#INV_${inv.id}\`\n` +
            `💰 Kiritilgan sarmoya: **${formatMoney(inv.amount)}**\n` +
            `📅 Muddat: **${inv.duration_days} kun**\n` +
            `🔥 Kunlik foyda: **25%** (+${formatMoney(dailyProfit)})\n` +
            `💸 Umumiy ko'rilgan foyda: **+${formatMoney(totalProfit)}**\n` +
            `💰 Balansingizga jami **${formatMoney(payout)}** o'tkazildi!`,
            { parse_mode: 'Markdown' }
          );
        } catch (err) {
          console.error(`Could not notify user ${inv.user_id} about completed investment:`, err);
        }
      }
    }
  } catch (error) {
    console.error('Error in checking completed investments:', error);
  }
}

// Run investment checker every 30 seconds
setInterval(checkCompletedInvestments, 30000);

// Launch bot
bot.launch()
  .then(() => {
    console.log('🚀 Investment & Referral Bot starts successfully!');
  })
  .catch((err) => {
    console.error('Failed to start Telegram Bot:', err);
  });

// Enable graceful stop
process.once('SIGINT', () => bot.stop('SIGINT'));
process.once('SIGTERM', () => bot.stop('SIGTERM'));

// Start a dummy HTTP server for Render port binding to prevent deployment failure
const PORT = process.env.PORT || 3000;
http.createServer((req, res) => {
  res.writeHead(200, { 'Content-Type': 'text/plain' });
  res.end('Bot is running successfully!\n');
}).listen(PORT, () => {
  console.log(`Web server listening on port ${PORT} to keep Render deployment alive.`);
});
