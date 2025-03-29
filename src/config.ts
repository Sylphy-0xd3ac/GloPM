// src/config.ts

/**
 * MongoDB 数据库连接字符串
 * 例如：'mongodb://localhost:27017/npmdb'
 */
export const MONGO_CONNECTION_STRING = process.env.MONGO_CONNECTION_STRING;

/**
 * 使用的数据库名称
 */
export const DB_NAME = process.env.DB_NAME;

/**
 * 服务监听的端口
 */
export const PORT = process.env.PORT;
