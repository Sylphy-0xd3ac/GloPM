// src/routes/authRoutes.ts
import Router from '@koa/router';
import { AuthController } from '../controllers/authController';
import { Db } from 'mongodb';
import { authenticate } from '../middlewares/auth';

/**
 * 用户认证相关路由
 */
export function authRoutes(db: Db): Router {
  const router = new Router({
    prefix: '/api/auth'
  });
  const authController = new AuthController(db);

  // 用户注册
  router.post('/register', async (ctx) => {
    await authController.register(ctx);
  });

  // 用户登录
  router.post('/login', async (ctx) => {
    await authController.login(ctx);
  });

  // 删除用户
  router.delete('/', authenticate(db), async (ctx) => {
    await authController.removeAccount(ctx);
  });

  return router;
}