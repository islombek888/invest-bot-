import dotenv from 'dotenv';
import path from 'path';

dotenv.config({ path: path.join(__dirname, '../../.env') });

export const config = {
  botToken: process.env.BOT_TOKEN || '',
  adminId: parseInt(process.env.ADMIN_ID || '0', 10),
  cardDetails: process.env.CARD_DETAILS || 'Karta raqami kiritilmagan',
  minDeposit: parseFloat(process.env.MIN_DEPOSIT || '20000'),
  minWithdrawal: parseFloat(process.env.MIN_WITHDRAWAL || '30000'),
  referralBonus: parseFloat(process.env.REFERRAL_BONUS || '1500'),
  minReferrals: parseInt(process.env.MIN_REFERRALS || '3', 10),
  dbPath: path.join(__dirname, '../../database.db'),
};
