// src/config.ts

/**
 * MongoDB 数据库连接字符串
 * 例如：'mongodb://localhost:27017/npmdb'
 */
export const MONGO_URI = process.env.MONGO_URI;

/**
 * 使用的数据库名称
 */
export const DB_NAME = process.env.DB_NAME;

/**
 * 服务监听的端口
 */
export const PORT = process.env.PORT;

/**
 * 账户密码(如有)
 */
export const ACCOUNT = process.env.MONGO_USERNAME ? process.env.USERNAME : null;
export const PASSWORD = process.env.PASSWORD ? process.env.PASSWORD : null;
